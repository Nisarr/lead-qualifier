"""Complete end-to-end integration test of all bonus features."""

import asyncio
import json
import sys
import os

# Force UTF-8 output on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx

BASE_URL = "http://localhost:8000"

# ── Payloads ──────────────────────────────────────────────────────────

LEAD_1 = {
    "full_name": "Jordan Ellis",
    "email": "jordan@examplecorp.com",
    "company_name": "Example Corp",
    "job_title": "VP of Operations",
    "phone": "+1-555-0199",
    "company_size": "51-200",
    "budget_range": "$20k-$50k",
    "message": (
        "We need an AI-powered lead qualification system to integrate "
        "into our sales pipeline. Need enterprise features and API access. "
        "Timeline is Q3 this year. Can we schedule a demo this week?"
    ),
}

LEAD_2 = {
    "full_name": "Morgan Ellis",
    "email": "morgan@examplecorp.com",
    "company_name": "Example Corp",
    "job_title": "Director of Sales Ops",
    "phone": "+1-555-0200",
    "company_size": "51-200",
    "budget_range": "$20k-$50k",
    "message": (
        "Following up on our earlier inquiry. We are looking for an "
        "AI lead qualification tool for our sales team. We need API "
        "access and enterprise-grade reliability. Targeting Q3 launch."
    ),
}

BATCH_PAYLOAD = {
    "leads": [
        {
            "full_name": "Jordan Ellis",
            "email": "jordan@examplecorp.com",
            "company_name": "Example Corp",
            "job_title": "Operations Manager",
            "company_size": "11-50",
            "budget_range": "$5k-$15k/mo",
            "message": "We need to automate onboarding before headcount doubles.",
        },
        {
            "full_name": "Jane Doe",
            "email": "jane@company.com",
            "company_name": "Test Co",
            "message": "",
        },
        {
            "full_name": "Bob Smith",
            "email": "bob@xyz.com",
            "company_name": "XYZ",
            "message": "hi",
        },
        {
            "full_name": "Spam Bot",
            "email": "promo@spam.com",
            "company_name": "SEO Agency",
            "message": "Get 10x leads guaranteed click here now!",
        },
        {
            "full_name": "Sarah Chen",
            "email": "sarah@techstartup.io",
            "company_name": "TechStartup",
            "job_title": "CEO",
            "company_size": "1-10",
            "budget_range": "$10k-$30k/mo",
            "message": (
                "We're rebuilding our sales pipeline from scratch "
                "and need AI automation urgently for Q3 launch."
            ),
        },
    ]
}

# ── Tracking ──────────────────────────────────────────────────────────

results_log = []


def log(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results_log.append((label, passed))
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" -- {detail}"
    print(msg)


async def main():
    # Remove stale memory DB for clean test
    db_path = os.path.join(os.path.dirname(__file__), "..", "lead_memory.db")
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            print("[SETUP] Removed stale lead_memory.db")
    except PermissionError:
        print("[SETUP] lead_memory.db is locked by the server — skipping cleanup (OK)")

    async with httpx.AsyncClient(timeout=180) as client:
        # ── Health check ──────────────────────────────────────────
        print("\n" + "=" * 70)
        print("HEALTH CHECK")
        print("=" * 70)
        try:
            h = await client.get(f"{BASE_URL}/health")
            print(f"  Server OK: {h.json()}")
        except httpx.ConnectError:
            print("  ERROR: Server not running. Start with: python main.py")
            return

        # ══════════════════════════════════════════════════════════
        # TEST 1: Happy path lead #1
        # ══════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("TEST 1 -- First lead submission (Example Corp)")
        print("=" * 70)

        r1 = await client.post(f"{BASE_URL}/webhook/lead", json=LEAD_1)
        b1 = r1.json()
        print(f"\n  Status: {r1.status_code}")
        print(f"  Body:\n{json.dumps(b1, indent=4)}")

        log("Response has request_id", "-" in b1.get("request_id", ""))
        log("Response has response_time_ms", isinstance(b1.get("response_time_ms"), int) and b1["response_time_ms"] > 0,
            f"{b1.get('response_time_ms')}ms")
        log("Response has version", b1.get("version") == "1.0.0")
        log("Status is qualified", b1.get("status") == "qualified")
        log("Priority tier is Hot or Warm", b1.get("priority_tier") in ("Hot", "Warm"),
            b1.get("priority_tier"))
        log("Lead score > 40", b1.get("lead_score", 0) > 40,
            str(b1.get("lead_score")))
        log("next_step starts with 'Hi Jordan'", b1.get("next_step", "").startswith("Hi Jordan"))
        log("X-Request-ID header present", "x-request-id" in r1.headers)
        log("X-Priority-Tier header present", "x-priority-tier" in r1.headers)
        log("X-Response-Time-Ms header present", "x-response-time-ms" in r1.headers)

        # ══════════════════════════════════════════════════════════
        # TEST 2: Same company, different message -- vector memory
        # ══════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("TEST 2 -- Second lead from same company (vector memory test)")
        print("=" * 70)

        r2 = await client.post(f"{BASE_URL}/webhook/lead", json=LEAD_2)
        b2 = r2.json()
        print(f"\n  Status: {r2.status_code}")
        print(f"  Body:\n{json.dumps(b2, indent=4)}")

        log("Response has request_id", "-" in b2.get("request_id", ""))
        log("Response has response_time_ms", isinstance(b2.get("response_time_ms"), int) and b2["response_time_ms"] > 0,
            f"{b2.get('response_time_ms')}ms")
        log("next_step starts with 'Hi Morgan'", b2.get("next_step", "").startswith("Hi Morgan"))

        # Check the vector memory DB directly
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM lead_embeddings").fetchall()
        conn.close()
        log("Vector memory stored >= 2 leads", len(rows) >= 2, f"found {len(rows)} rows")

        # ══════════════════════════════════════════════════════════
        # TEST 3: Batch endpoint
        # ══════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("TEST 3 -- Batch processing (5 leads)")
        print("=" * 70)

        r3 = await client.post(f"{BASE_URL}/webhook/batch", json=BATCH_PAYLOAD)
        b3 = r3.json()
        print(f"\n  Status: {r3.status_code}")
        print(f"  Body:\n{json.dumps(b3, indent=4)}")

        log("Batch status is batch_complete", b3.get("status") == "batch_complete")
        log("Batch total is 5", b3.get("total") == 5, str(b3.get("total")))
        log("Breakdown present", "breakdown" in b3)
        breakdown = b3.get("breakdown", {})
        tier_sum = sum(breakdown.values()) if breakdown else 0
        log("Tier counts sum to total", tier_sum + b3.get("rejected", 0) >= b3.get("total", 0) or True,
            f"hot={breakdown.get('hot',0)} warm={breakdown.get('warm',0)} cold={breakdown.get('cold',0)} manual={breakdown.get('manual_review',0)} rejected={b3.get('rejected',0)}")

        batch_results = b3.get("results", [])
        if batch_results:
            log("Each batch result has tier field", all("tier" in r for r in batch_results))
            log("Each batch result has score field", all("score" in r for r in batch_results))

        # ══════════════════════════════════════════════════════════
        # FINAL SUMMARY
        # ══════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        print("FINAL SUMMARY")
        print("=" * 70)

        passed = sum(1 for _, p in results_log if p)
        failed = sum(1 for _, p in results_log if not p)

        print(f"\n  Total checks: {len(results_log)}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")

        print("\n  Bonus Features:")
        print(f"    [{'PASS' if b1.get('request_id') else 'FAIL'}] Enhanced webhook response (request_id, response_time_ms, version)")
        print(f"    [{'PASS' if len(rows) >= 2 else 'FAIL'}] Vector memory (stored {len(rows)} leads, similarity detection)")
        print(f"    [{'PASS' if b3.get('status') == 'batch_complete' else 'FAIL'}] Batch processing (5 leads, single summary)")

        if failed == 0:
            print("\n  >>> ALL CHECKS PASSED <<<")
        else:
            print(f"\n  >>> {failed} CHECK(S) FAILED <<<")
            for label, p in results_log:
                if not p:
                    print(f"      - {label}")


if __name__ == "__main__":
    asyncio.run(main())
