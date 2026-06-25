"""Test enhanced webhook response: request tracking, personalization, and timeout fallback."""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx

BASE_URL = "http://localhost:8000"

HAPPY_PAYLOAD = {
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


async def main():
    async with httpx.AsyncClient(timeout=120) as client:
        # ── Health check ──────────────────────────────────────────────
        try:
            health = await client.get(f"{BASE_URL}/health")
            print(f"[HEALTH] {health.json()}\n")
        except httpx.ConnectError:
            print("ERROR: Server not running. Start with: python main.py")
            return

        # ── Test 1: Happy path ────────────────────────────────────────
        print("=" * 70)
        print("TEST 1 — Happy path (normal lead)")
        print("=" * 70)

        resp = await client.post(f"{BASE_URL}/webhook/lead", json=HAPPY_PAYLOAD)
        body = resp.json()

        print(f"\nStatus code: {resp.status_code}")
        print(f"\nResponse headers:")
        print(f"  X-Request-ID:       {resp.headers.get('X-Request-ID', 'MISSING')}")
        print(f"  X-Priority-Tier:    {resp.headers.get('X-Priority-Tier', 'MISSING')}")
        print(f"  X-Response-Time-Ms: {resp.headers.get('X-Response-Time-Ms', 'MISSING')}")
        print(f"\nResponse body:")
        print(json.dumps(body, indent=2))

        # Validate response fields
        print("\n-- Validation --")
        checks = {
            "request_id is UUID format": "-" in body.get("request_id", ""),
            "status is 'qualified'": body.get("status") == "qualified",
            "priority_tier present": body.get("priority_tier") in ("Hot", "Warm", "Cold", "Manual Review"),
            "lead_score > 0": body.get("lead_score", 0) > 0,
            "next_step starts with 'Hi Jordan'": body.get("next_step", "").startswith("Hi Jordan"),
            "response_time_ms is real number": isinstance(body.get("response_time_ms"), int) and body["response_time_ms"] > 0,
            "version is '1.0.0'": body.get("version") == "1.0.0",
        }
        for check, passed in checks.items():
            icon = "PASS" if passed else "FAIL"
            print(f"  [{icon}] {check}")

        all_passed = all(checks.values())
        print(f"\n{'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
