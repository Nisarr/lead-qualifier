"""AI-based scoring and evaluation of leads using Anthropic."""

import asyncio
import json
import re

import anthropic
from anthropic import AsyncAnthropic

from config import ANTHROPIC_API_KEY
from models import AIAnalysis, NormalizedLead

LEAD_SCORING_SYSTEM_PROMPT = """
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


async def score_lead(lead: NormalizedLead) -> AIAnalysis:
    # Guard: if message is empty or None, skip the API call entirely
    if not lead.message:
        return _FALLBACK

    # Build a lean user prompt — only the fields the model needs
    user_prompt = (
        f"Company: {lead.company_name}\n"
        f"Title: {lead.job_title}\n"
        f"Size: {lead.company_size}\n"
        f"Budget: {lead.budget_range}\n"
        f"Message: {lead.message}"
    )

    try:
        client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            temperature=0.1,
            system=LEAD_SCORING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = response.content[0].text if response.content else ""

        # Parse response: first attempt a direct json.loads()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: extract a JSON object from the text using regex
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                print(f"[AI_SCORER ERROR] JSONDecodeError: Could not extract JSON from response: {text!r}")
                return _FALLBACK

        return AIAnalysis(**parsed)

    except anthropic.RateLimitError as e:
        print(f"[AI_SCORER ERROR] {type(e).__name__}: {e}")
        return _FALLBACK
    except anthropic.APIError as e:
        print(f"[AI_SCORER ERROR] {type(e).__name__}: {e}")
        return _FALLBACK
    except asyncio.TimeoutError as e:
        print(f"[AI_SCORER ERROR] {type(e).__name__}: {e}")
        return _FALLBACK
    except json.JSONDecodeError as e:
        print(f"[AI_SCORER ERROR] {type(e).__name__}: {e}")
        return _FALLBACK
    except Exception as e:
        print(f"[AI_SCORER ERROR] {type(e).__name__}: {e}")
        return _FALLBACK
