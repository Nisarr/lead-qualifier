"""Orchestrates the overall lead qualification pipeline."""

from datetime import datetime, timezone

from ai_scorer import score_lead
from models import EnrichedLead, WebhookResponse
from notifier import send_slack_notification
from sheets_writer import write_to_sheets
from validator import validate_and_normalize


async def run_pipeline(raw_data: dict) -> WebhookResponse:

    # STEP 1 — Validate & Normalize
    result, error_code = validate_and_normalize(raw_data)

    if error_code == "missing_required_fields":
        stub = _make_error_stub(raw_data, error_code)
        write_to_sheets(stub)           # Log rejected leads so Sheets is a complete audit trail
        send_slack_notification(stub)
        return WebhookResponse(
            status="rejected",
            priority_tier="Invalid",
            lead_score=0,
            next_step="Submission rejected: missing required fields.",
        )

    if error_code == "invalid_email_format":
        stub = _make_error_stub(raw_data, error_code)
        write_to_sheets(stub)           # Log even bad-email leads for analytics
        return WebhookResponse(
            status="rejected",
            priority_tier="Invalid",
            lead_score=0,
            next_step="Submission rejected: invalid email format.",
        )

    if error_code == "low_context_message":
        # Build a lightweight stub and route through the standard notification path
        stub = _make_error_stub(raw_data, error_code, score=5, tier="Cold")
        write_to_sheets(stub)
        send_slack_notification(stub)
        return WebhookResponse(
            status="low_context",
            priority_tier="Cold",
            lead_score=5,
            next_step="Your message was too brief. We'll be in touch if we can help.",
        )

    # If the error_code is something unexpected (e.g. model_validation_failed), handle gracefully
    if error_code is not None:
        stub = _make_error_stub(raw_data, error_code)
        write_to_sheets(stub)
        send_slack_notification(stub)
        return WebhookResponse(
            status="rejected",
            priority_tier="Invalid",
            lead_score=0,
            next_step="Submission could not be processed.",
        )

    # STEP 2 — AI Scoring
    analysis = await score_lead(result)

    # STEP 3 — Merge NormalizedLead + AIAnalysis into a single EnrichedLead
    enriched = EnrichedLead(**result.model_dump(), **analysis.model_dump())

    # STEP 4 — Write to Google Sheets (non-blocking; failure does NOT stop the pipeline)
    write_to_sheets(enriched)

    # STEP 5 — Send Slack Notification
    send_slack_notification(enriched)

    # STEP 6 — Build and return the synchronous WebhookResponse
    next_step_map = {
        "Hot": "Our team will reach out within 2 hours. " + enriched.suggested_opener,
        "Warm": "We'll review your inquiry and be in touch within 24 hours.",
        "Cold": "Thank you for reaching out. We'll review and follow up if there's a fit.",
        "Manual Review": "We received your message and will follow up shortly.",
    }

    return WebhookResponse(
        status="qualified",
        priority_tier=enriched.priority_tier,
        lead_score=enriched.lead_score,
        next_step=next_step_map.get(
            enriched.priority_tier,
            "We received your message and will follow up shortly.",
        ),
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
