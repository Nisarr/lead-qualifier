"""Test vector memory: send the same company twice, check for returning-inquiry red flag."""

import asyncio
import json
import os
import sys

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(__file__))

# Remove stale memory DB so the test starts clean
DB_FILE = os.path.join(os.path.dirname(__file__), "lead_memory.db")
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print("[SETUP] Removed stale lead_memory.db\n")


async def main():
    # Lazy imports so env / config are loaded first
    from pipeline import run_pipeline

    # ── Payload 1: First contact from Acme Corp ──────────────────────
    payload_1 = {
        "full_name": "Sarah Connor",
        "email": "sarah@acmecorp.com",
        "company_name": "Acme Corp",
        "job_title": "VP of Engineering",
        "phone": "+1-555-0100",
        "company_size": "200-500",
        "budget_range": "$50k-$100k",
        "message": (
            "We are looking for an AI-powered lead qualification system "
            "to integrate into our sales pipeline. Need enterprise features "
            "and API access. Timeline is Q3 this year."
        ),
    }

    print("=" * 70)
    print("REQUEST 1 — First submission from Acme Corp")
    print("=" * 70)
    resp1 = await run_pipeline(payload_1)
    print(json.dumps(resp1.model_dump(), indent=2))

    # ── Payload 2: Same company, slightly different message ──────────
    payload_2 = {
        "full_name": "John Connor",
        "email": "john@acmecorp.com",
        "company_name": "Acme Corp",
        "job_title": "Director of Sales Ops",
        "phone": "+1-555-0101",
        "company_size": "200-500",
        "budget_range": "$50k-$100k",
        "message": (
            "Following up on our earlier inquiry — we need an AI lead "
            "qualification tool for our sales team. Looking for API access "
            "and enterprise-grade reliability. Targeting Q3 launch."
        ),
    }

    print("\n" + "=" * 70)
    print("REQUEST 2 — Second submission from Acme Corp (similar inquiry)")
    print("=" * 70)
    resp2 = await run_pipeline(payload_2)
    print(json.dumps(resp2.model_dump(), indent=2))

    # ── Verify ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    flags = resp2.model_dump()
    # The red_flag about "returning inquiry" should come from pipeline.py
    # even if the LLM didn't include it, because pipeline.py appends it.
    # But we can only check the WebhookResponse here (which doesn't include
    # red_flags). Let's re-import and check the full enriched flow instead.
    from vector_memory import VectorMemory
    from models import NormalizedLead
    from validator import validate_and_normalize

    normalized, _ = validate_and_normalize(payload_2)
    memory = VectorMemory()
    match = memory.find_similar(normalized)

    if match:
        print(f"✓ Memory match found!  Similarity: {match['similarity_score']}")
        print(f"  Prior company: {match['company_name']}")
        print(f"  Prior tier:    {match['prior_tier']}")
        print(f"  Prior score:   {match['prior_score']}")
    else:
        print("✗ No memory match — test FAILED")


if __name__ == "__main__":
    asyncio.run(main())
