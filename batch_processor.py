"""Batch processing engine for qualifying multiple leads concurrently."""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass, field

from models import LeadInput, EnrichedLead
from pipeline import run_pipeline

# ── Constants ──────────────────────────────────────────────────────────

MAX_CONCURRENT_AI_CALLS = 3    # Semaphore limit
RATE_LIMIT_DELAY = 0.5         # seconds between batches


@dataclass
class BatchResult:
    """Aggregated stats and per-lead results from a batch run."""

    total: int = 0
    processed: int = 0
    rejected: int = 0
    hot_count: int = 0
    warm_count: int = 0
    cold_count: int = 0
    manual_review_count: int = 0
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Core batch runner ──────────────────────────────────────────────────

async def process_batch(leads_data: list[dict]) -> BatchResult:
    """Run every lead in *leads_data* through the pipeline concurrently.

    Concurrency is capped by ``MAX_CONCURRENT_AI_CALLS`` and a short
    delay is injected between completions to stay under rate limits.
    """
    batch = BatchResult(total=len(leads_data))
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_CALLS)

    async def process_single(raw: dict) -> dict:
        async with semaphore:
            try:
                response = await run_pipeline(raw)
                await asyncio.sleep(RATE_LIMIT_DELAY)
                return {
                    "name": raw.get("full_name", "Unknown"),
                    "company": raw.get("company_name", "Unknown"),
                    "tier": response.priority_tier,
                    "score": response.lead_score,
                    "status": response.status,
                    "next_step": response.next_step,
                }
            except Exception as e:
                return {"error": str(e), "raw": raw}

    tasks = [process_single(lead) for lead in leads_data]
    results = await asyncio.gather(*tasks)

    for res in results:
        if "error" in res:
            batch.errors.append(res["error"])
            batch.rejected += 1
        else:
            batch.results.append(res)

            status = res.get("status", "")
            if status in ("rejected", "low_context"):
                batch.rejected += 1
            else:
                batch.processed += 1

            tier = res.get("tier", "")
            if tier == "Hot":
                batch.hot_count += 1
            elif tier == "Warm":
                batch.warm_count += 1
            elif tier == "Cold":
                batch.cold_count += 1
            elif tier in ("Manual Review", "Invalid"):
                batch.manual_review_count += 1

    return batch


# ── CSV helper ─────────────────────────────────────────────────────────

def parse_csv(csv_text: str) -> list[dict]:
    """Parse a CSV string into a list of dicts matching LeadInput fields.

    Skips rows where every field is empty.  Returns ``[]`` on any error.
    """
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        leads: list[dict] = []
        for row in reader:
            # Skip fully-blank rows
            if all(not v or not v.strip() for v in row.values()):
                continue
            leads.append({k: (v.strip() if v else "") for k, v in row.items()})
        return leads
    except Exception as e:
        print(f"[BATCH] CSV parse error: {e}")
        return []
