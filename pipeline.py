"""Orchestrates the overall lead qualification pipeline."""

import asyncio
import time
import uuid
from datetime import datetime, timezone

from ai_scorer import score_lead
from models import AIAnalysis, EnrichedLead, WebhookResponse
from notifier import send_slack_notification
from sheets_writer import write_to_sheets
from validator import validate_and_normalize
from vector_memory import VectorMemory

import config


# ── Personalized next-step builder ─────────────────────────────────────

def _build_next_step(enriched: EnrichedLead) -> str:
    """Build a personalized next-step message based on tier and name."""
    tier = enriched.priority_tier
    name = enriched.full_name.split()[0]  # first name only

    if tier == "Hot":
        return (
            f"Hi {name}, thank you for reaching out to us. "
            f"Based on what you've shared, we can definitely help. "
            f"{enriched.suggested_opener} "
            f"Expect a call from our team within 2 hours."
        )
    elif tier == "Warm":
        return (
            f"Hi {name}, thanks for getting in touch. "
            f"We've received your inquiry and a specialist will "
            f"review it and follow up within 24 hours."
        )
    elif tier == "Cold":
        return (
            f"Hi {name}, thank you for your message. "
            f"We'll review your inquiry and reach out if there's "
            f"a strong fit for our services."
        )
    else:  # Manual Review or timeout
        return (
            f"Hi {name}, we've received your message "
            f"and will get back to you shortly."
        )


# ── Main pipeline ─────────────────────────────────────────────────────

async def run_pipeline(raw_data: dict) -> WebhookResponse:

    request_id = str(uuid.uuid4())
    start_time = time.time()

    # STEP 1 — Validate & Normalize
    result, error_code = validate_and_normalize(raw_data)

    if error_code == "missing_required_fields":
        stub = _make_error_stub(raw_data, error_code)
        write_to_sheets(stub)           # Log rejected leads so Sheets is a complete audit trail
        send_slack_notification(stub)
        return WebhookResponse(
            request_id=request_id,
            status="rejected",
            priority_tier="Invalid",
            lead_score=0,
            next_step="Submission rejected: missing required fields.",
            response_time_ms=int((time.time() - start_time) * 1000),
            version=config.APP_VERSION,
        )

    if error_code == "invalid_email_format":
        stub = _make_error_stub(raw_data, error_code)
        write_to_sheets(stub)           # Log even bad-email leads for analytics
        return WebhookResponse(
            request_id=request_id,
            status="rejected",
            priority_tier="Invalid",
            lead_score=0,
            next_step="Submission rejected: invalid email format.",
            response_time_ms=int((time.time() - start_time) * 1000),
            version=config.APP_VERSION,
        )

    if error_code == "low_context_message":
        # Build a lightweight stub and route through the standard notification path
        stub = _make_error_stub(raw_data, error_code, score=5, tier="Cold")
        write_to_sheets(stub)
        send_slack_notification(stub)
        return WebhookResponse(
            request_id=request_id,
            status="low_context",
            priority_tier="Cold",
            lead_score=5,
            next_step="Your message was too brief. We'll be in touch if we can help.",
            response_time_ms=int((time.time() - start_time) * 1000),
            version=config.APP_VERSION,
        )

    # If the error_code is something unexpected (e.g. model_validation_failed), handle gracefully
    if error_code is not None:
        stub = _make_error_stub(raw_data, error_code)
        write_to_sheets(stub)
        send_slack_notification(stub)
        return WebhookResponse(
            request_id=request_id,
            status="rejected",
            priority_tier="Invalid",
            lead_score=0,
            next_step="Submission could not be processed.",
            response_time_ms=int((time.time() - start_time) * 1000),
            version=config.APP_VERSION,
        )

    # ── Memory lookup ──────────────────────────────────────────────────
    memory = VectorMemory()
    prior_context = memory.find_similar(result)

    # STEP 2 — AI Scoring (with timeout protection)
    try:
        analysis = await asyncio.wait_for(
            score_lead(result, prior_context=prior_context),
            timeout=config.WEBHOOK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] Request {request_id} exceeded {config.WEBHOOK_TIMEOUT_SECONDS}s")
        analysis = AIAnalysis(
            lead_score=0,
            priority_tier="Manual Review",
            intent_summary="AI timed out — routed to manual review.",
            suggested_opener="",
            red_flags=["ai_timeout"],
        )

    # Store this lead for future memory
    memory.store_lead(result, analysis.lead_score, analysis.priority_tier)

    # If prior context found, add to red_flags if not already there
    if prior_context and "returning" not in str(analysis.red_flags):
        analysis.red_flags.append(
            f"returning inquiry - similar to prior {prior_context['prior_tier']} lead"
        )

    # STEP 3 — Merge NormalizedLead + AIAnalysis into a single EnrichedLead
    enriched = EnrichedLead(**result.model_dump(), **analysis.model_dump())

    # STEP 4 — Write to Google Sheets (non-blocking; failure does NOT stop the pipeline)
    write_to_sheets(enriched)

    # STEP 5 — Send Slack Notification
    send_slack_notification(enriched)

    # STEP 6 — Build and return the enhanced WebhookResponse
    response_time_ms = int((time.time() - start_time) * 1000)

    return WebhookResponse(
        request_id=request_id,
        status="timeout" if "ai_timeout" in analysis.red_flags else "qualified",
        priority_tier=enriched.priority_tier,
        lead_score=enriched.lead_score,
        next_step=_build_next_step(enriched),
        response_time_ms=response_time_ms,
        version=config.APP_VERSION,
    )


def _make_error_stub(
    raw_data: dict,
    error_code: str,
    *,
    score: int = 0,
    tier: str = "Manual Review",
) -> EnrichedLead:
    """Build a minimal EnrichedLead for error-path logging and notifications."""
    now = datetime.now(timezone.utc).isoformat()
    return EnrichedLead(
        full_name=str(raw_data.get("full_name", "Unknown")).strip() or "Unknown",
        email=str(raw_data.get("email", "unknown@unknown.com")).strip() or "unknown@unknown.com",
        company_name=str(raw_data.get("company_name", "N/A")).strip() or "N/A",
        job_title=str(raw_data.get("job_title", "N/A")).strip() or "N/A",
        phone=str(raw_data.get("phone", "N/A")).strip() or "N/A",
        company_size=str(raw_data.get("company_size", "N/A")).strip() or "N/A",
        budget_range=str(raw_data.get("budget_range", "N/A")).strip() or "N/A",
        message=str(raw_data.get("message", "N/A")).strip() or "N/A",
        timestamp=now,
        lead_score=score,
        priority_tier=tier,
        intent_summary=f"Rejected submission — {error_code}",
        suggested_opener="",
        red_flags=[error_code],
    )
