"""Main entry point for the lead qualification system."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
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
from models import LeadInput, WebhookResponse
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


@app.post("/webhook/lead", response_model=WebhookResponse)
async def webhook_lead(lead: LeadInput) -> WebhookResponse:
    """
    Receive a lead submission, run the full qualification pipeline
    (validate → AI score → Sheets → Slack), and return a real-time
    WebhookResponse to the caller (Bonus Option C).
    """
    response = await run_pipeline(lead.model_dump())
    return response


@app.get("/", include_in_schema=False)
async def root():
    """Serve the contact form at the root URL."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
async def health():
    """Liveness check — returns ok when the service is running."""
    return {"status": "ok", "service": "lead-qualifier"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
