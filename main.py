"""Main entry point for the lead qualification system."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Body, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure stdout handles UTF-8 (e.g. checkmark icon) on Windows consoles without throwing UnicodeEncodeError
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config  # noqa: F401 — imported for side-effect: raises ValueError on missing env vars
from batch_processor import process_batch, parse_csv
from models import LeadInput, WebhookResponse
from notifier import send_batch_summary
from pipeline import run_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: config import above already validated all env vars.
    # If we reach here, all required variables are present.
    print("[STARTUP] Lead Qualifier API running ✓")
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(title="Lead Qualification API", lifespan=lifespan)

# CORS middleware — allow all origins for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/webhook/lead")
async def webhook_lead(lead: LeadInput, response: Response):
    """
    Receive a lead submission, run the full qualification pipeline
    (validate → AI score → Sheets → Slack), and return a real-time
    WebhookResponse with tracking headers.
    """
    result = await run_pipeline(lead.model_dump())

    # Set headers useful for the caller
    response.headers["X-Request-ID"] = result.request_id
    response.headers["X-Priority-Tier"] = result.priority_tier
    response.headers["X-Response-Time-Ms"] = str(result.response_time_ms)

    return result


@app.post("/webhook/batch")
async def batch_webhook_json(payload: dict = Body(...)):
    """Accept a batch of leads as a JSON body.

    **JSON body** — ``{"leads": [ … ]}`` with up to 50 LeadInput dicts.
    """
    if "leads" not in payload:
        return {"error": "Provide JSON body with {\"leads\":[...]}"}
    return await _run_batch(payload["leads"])


@app.post("/webhook/batch/csv")
async def batch_webhook_csv(file: UploadFile = File(...)):
    """Accept a batch of leads as a CSV file upload.

    **CSV upload** — multipart form with a ``file`` field; column headers
    must match LeadInput fields.
    """
    content = await file.read()
    leads_data = parse_csv(content.decode("utf-8"))
    return await _run_batch(leads_data)


async def _run_batch(leads_data: list[dict]) -> dict:
    """Shared batch processing logic for both JSON and CSV routes."""
    if not leads_data:
        return {"error": "No valid leads found in the request"}

    if len(leads_data) > 50:
        return {"error": "Batch limit is 50 leads per request"}

    # Process the batch
    result = await process_batch(leads_data)

    # Send consolidated Slack notification
    send_batch_summary(result)

    return {
        "status": "batch_complete",
        "total": result.total,
        "processed": result.processed,
        "rejected": result.rejected,
        "breakdown": {
            "hot": result.hot_count,
            "warm": result.warm_count,
            "cold": result.cold_count,
            "manual_review": result.manual_review_count,
        },
        "results": result.results,
    }


@app.get("/", include_in_schema=False)
async def root():
    """Serve the contact form at the root URL."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/batch", include_in_schema=False)
async def batch_ui():
    """Serve the batch upload form at the /batch URL."""
    return FileResponse(Path(__file__).parent / "static" / "batch.html")


@app.get("/health")
async def health():
    """Liveness check — returns ok when the service is running."""
    return {"status": "ok", "service": "lead-qualifier"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

