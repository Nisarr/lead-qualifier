"""AI-powered lead scoring with multi-provider fallback chain.

Provider priority: Gemini 2.0 Flash Lite → GitHub Models (GPT-4o-mini) → Anthropic Claude Haiku.
If all providers fail, a static fallback is returned so the pipeline never crashes.
"""

import asyncio
import json
import re

from openai import AsyncOpenAI
from pydantic import ValidationError

import config
from models import AIAnalysis, NormalizedLead

# ── Constants ──────────────────────────────────────────────────────────

API_TIMEOUT_SECONDS = 15  # Per-provider timeout to prevent hanging

LEAD_SCORING_SYSTEM_PROMPT = """\
You are a senior B2B sales qualification specialist with 10 years of experience.
Your task is to analyze an inbound lead inquiry and return a structured qualification score.

CRITICAL: Return ONLY a raw JSON object. No markdown. No code fences. No explanation.
No text before or after the JSON. The response must be parseable by json.loads() directly.

Output schema (return exactly these keys):
{
  "lead_score": <integer 1-100>,
  "priority_tier": <"Hot" | "Warm" | "Cold">,
  "intent_summary": <one sentence, max 20 words, describing what they want>,
  "suggested_opener": <1-2 sentence personalized email opener for a sales rep>,
  "red_flags": <array of short strings, or empty array []>
}

Scoring guide:
- Hot (75-100): Clear pain point, budget signal, decision-maker title, urgency language
- Warm (40-74): Some intent but missing budget, vague timeline, or junior title
- Cold (1-39): Vague message, no business context, spam signals, student inquiry, competitor

Red flag examples: "no budget signal", "student inquiry", "looks like spam",
"competitor research", "no decision-making authority", "too vague to qualify"
"""

_FALLBACK = AIAnalysis(
    lead_score=0,
    priority_tier="Manual Review",
    intent_summary="AI processing unavailable — manual review required.",
    suggested_opener="",
    red_flags=["ai_error"],
)


# ── Parsing ────────────────────────────────────────────────────────────

def _parse_response(text: str) -> AIAnalysis:
    """Parse an LLM text response into an AIAnalysis, with two-stage fallback.

    Stage 1: Attempt direct json.loads() on the full text.
    Stage 2: Regex-extract the first {...} block and parse that.
    If both fail, or the parsed dict doesn't match the AIAnalysis schema, return _FALLBACK.
    """
    for candidate in _extract_json_candidates(text):
        try:
            parsed = json.loads(candidate)
            return AIAnalysis(**parsed)
        except (json.JSONDecodeError, ValidationError, TypeError):
            continue
    return _FALLBACK


def _extract_json_candidates(text: str) -> list[str]:
    """Yield JSON string candidates: full text first, then regex-extracted block."""
    candidates = [text]
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        candidates.append(match.group())
    return candidates


# ── Provider Calls ─────────────────────────────────────────────────────

async def _call_openai_compatible(
    api_key: str,
    base_url: str,
    model: str,
    user_prompt: str,
    label: str,
) -> AIAnalysis:
    """Call an OpenAI-compatible API with timeout and parse the result."""
    print(f"[AI_SCORER] Attempting {label} ({model})...")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LEAD_SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=512,
        ),
        timeout=API_TIMEOUT_SECONDS,
    )
    text = response.choices[0].message.content or ""
    return _parse_response(text)


async def _call_anthropic(api_key: str, user_prompt: str) -> AIAnalysis:
    """Call Anthropic's native SDK with timeout and parse the result."""
    print("[AI_SCORER] Attempting Anthropic (claude-haiku-4-5-20251001)...")
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await asyncio.wait_for(
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=LEAD_SCORING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.1,
        ),
        timeout=API_TIMEOUT_SECONDS,
    )
    text = response.content[0].text if response.content else ""
    return _parse_response(text)


# ── Main Entry Point ──────────────────────────────────────────────────

async def score_lead(
    lead: NormalizedLead, prior_context: dict | None = None
) -> AIAnalysis:
    """Score a lead using a multi-provider fallback chain.

    Only the fields the AI needs for reasoning are sent — not the full payload.
    If *prior_context* is supplied (from vector memory), it is appended so the
    LLM can factor repeat-inquiry signals into its analysis.
    """
    if not lead.message or not lead.message.strip():
        return _FALLBACK

    # Token-efficient: send only the 5 fields the model needs to score the lead
    user_prompt = (
        f"Company: {lead.company_name}\n"
        f"Title: {lead.job_title}\n"
        f"Size: {lead.company_size}\n"
        f"Budget: {lead.budget_range}\n"
        f"Message: {lead.message}"
    )

    # Inject memory context when a similar prior lead was detected
    if prior_context is not None:
        user_prompt += (
            f"\n\n⚠️ MEMORY CONTEXT — Similar inquiry detected:\n"
            f"Prior company: {prior_context['company_name']}\n"
            f"Prior qualification: {prior_context['prior_tier']} "
            f"(score: {prior_context['prior_score']})\n"
            f"Similarity: {prior_context['similarity_score']}\n"
            f"Prior message preview: {prior_context['message_preview']}\n\n"
            f"Factor this into your analysis. If this appears to be a returning "
            f"company or repeat inquiry, note it in red_flags as "
            f"\"returning inquiry - prior tier: {prior_context['prior_tier']}\""
        )

    # Provider 1: Gemini 2.0 Flash Lite via OpenAI Compatibility Layer
    if config.GEMINI_API_KEY:
        try:
            return await _call_openai_compatible(
                api_key=config.GEMINI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model="gemini-2.0-flash-lite",
                user_prompt=user_prompt,
                label="Gemini 2.0 Flash Lite",
            )
        except Exception as e:
            print(f"[AI_SCORER ERROR] Gemini failed ({type(e).__name__}: {e}). Trying fallback...")

    # Provider 2: GitHub Models (GPT-4o-mini)
    if config.GITHUB_TOKEN:
        try:
            return await _call_openai_compatible(
                api_key=config.GITHUB_TOKEN,
                base_url="https://models.inference.ai.azure.com",
                model="gpt-4o-mini",
                user_prompt=user_prompt,
                label="GitHub Models",
            )
        except Exception as e:
            print(f"[AI_SCORER ERROR] GitHub Models failed ({type(e).__name__}: {e}). Trying fallback...")

    # Provider 3: Anthropic Claude Haiku
    if config.ANTHROPIC_API_KEY:
        try:
            return await _call_anthropic(
                api_key=config.ANTHROPIC_API_KEY,
                user_prompt=user_prompt,
            )
        except Exception as e:
            print(f"[AI_SCORER ERROR] Anthropic failed ({type(e).__name__}: {e})")

    print("[AI_SCORER ERROR] All AI providers failed or were not configured.")
    return _FALLBACK
