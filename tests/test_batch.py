"""Test batch processing endpoint — sends 5 leads via POST /webhook/batch."""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx


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


async def main():
    base_url = "http://localhost:8000"

    # Quick health check
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            health = await client.get(f"{base_url}/health")
            print(f"[HEALTH] {health.json()}\n")
        except httpx.ConnectError:
            print("ERROR: Server not running. Start with: python main.py")
            return

        print("=" * 70)
        print("SENDING BATCH REQUEST — 5 leads")
        print("=" * 70)

        resp = await client.post(
            f"{base_url}/webhook/batch",
            json=BATCH_PAYLOAD,
        )

        print(f"\nStatus code: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
