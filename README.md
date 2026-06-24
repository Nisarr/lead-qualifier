# Lead Qualification Automation — Aspire Tech Assessment

A FastAPI-based B2B lead qualification system that validates, AI-scores, logs, and notifies on inbound sales leads in real-time.

---

## Architecture Overview

Every lead submission flows through a strict 4-step pipeline before a response is returned to the caller:

```
                         ┌────────────────────────────────────────────────────┐
  Webhook Caller         │               Lead Qualifier Pipeline               │
  ─────────────          │                                                     │
                         │  1. TRIGGER       2. FILTER        3. AI           │
  POST /webhook/lead ───►│  ───────────      ────────         ────────        │
                         │  Receive raw  → Validate &  →  Claude Haiku    →  │
                         │  JSON payload    normalize      scores lead        │
                         │                  (reject bad    (1–100 score,      │
                         │                   inputs)        tier, opener,     │
                         │                                  red flags)        │
                         │                                        │            │
                         │                           4. OUTPUT    ▼            │
                         │                           ─────────────             │
                         │                         ┌──────────────────┐       │
                         │                         │  Google Sheets   │       │
                         │                         │  (append row)    │       │
                         │                         └──────────────────┘       │
                         │                         ┌──────────────────┐       │
                         │                         │  Slack Notify    │       │
                         │                         │  (Block Kit msg) │       │
                         │                         └──────────────────┘       │
                         │                                        │            │
  ◄── WebhookResponse ───│◄───────────────────────────────────────            │
  (real-time JSON)        └────────────────────────────────────────────────────┘
```

**Validation failures** (missing fields, bad email, too-short message) are short-circuited before any AI call, saving tokens and cost.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| API Framework | **FastAPI** 0.128+ with `uvicorn` ASGI server |
| Language | **Python 3.11+** (compatible with 3.13) |
| AI Scoring | **Anthropic Claude Haiku** (`claude-haiku-4-5-20251001`) |
| Data Validation | **Pydantic v2** with strict field constraints |
| Lead Logging | **Google Sheets API** via `gspread` + service account auth |
| Notifications | **Slack SDK** (`slack-sdk`) with Block Kit messages |
| Config | `python-dotenv` for environment variable management |
| HTTP Client | `httpx` (async-capable, used in tests) |
| Testing | `pytest` with live server integration tests |

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone <repo-url>
cd lead-qualifier
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SHEETS_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_CREDENTIALS_PATH=credentials.json
SLACK_BOT_TOKEN=xoxb-...
SLACK_HOT_CHANNEL=#hot-leads
SLACK_GENERAL_CHANNEL=#leads-incoming
```

### 4. Set up Google Sheets credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Create a new project
2. Enable the **Google Sheets API** and **Google Drive API**
3. Create a **Service Account** → Download the JSON key → save as `credentials.json` in the project root
4. Share your target Google Sheet with the service account email (Editor access)

### 5. Configure Slack

1. Create a Slack App at [api.slack.com](https://api.slack.com/apps)
2. Add Bot Token Scopes: `chat:write`, `chat:write.public`
3. Install the app to your workspace and copy the **Bot Token** into `.env`

### 6. Start the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it is running:

```bash
curl http://localhost:8000/health
# → {"status": "ok", "service": "lead-qualifier"}
```

### 7. Run tests

```bash
python -m pytest tests/ -v -s
```

---

## Key Design Decisions

### Validation before AI (token efficiency & cost)
The `validate_and_normalize` step runs entirely locally with zero API calls. Leads with missing required fields, invalid email formats, or messages shorter than 10 characters are rejected or flagged before any Anthropic API call is made. This eliminates unnecessary token spend on obviously invalid submissions and keeps latency low for bad actors.

### Claude Haiku (speed + cost for structured output)
Claude Haiku is the fastest and most cost-efficient Claude model, purpose-built for tasks that require structured, consistent output rather than open-ended reasoning. Scoring a lead requires extracting a JSON object with 5 defined fields — this is exactly the task profile Haiku excels at. Sonnet or Opus would be slower and ~10–50× more expensive per call with no quality benefit for this task.

### Temperature = 0.1 (consistent, repeatable scoring)
Lead scoring must be deterministic across similar inputs. A temperature near 0 minimises token sampling randomness, ensuring the same lead profile receives a similar score on repeat calls. This is important for auditability and for the Sheets log to be trustworthy over time.

### System prompt separated from lead data
The `LEAD_SCORING_SYSTEM_PROMPT` is a module-level constant passed as the `system` parameter, not injected into the user message. This leverages Anthropic's native system prompt caching, keeps the user message lean (5 fields only), and maintains a clean separation between instructions and data — making the prompt easier to iterate on without touching the scoring logic.

### Synchronous webhook response (Bonus Option C)
Rather than acknowledging the webhook and processing asynchronously, the endpoint `await`s the full pipeline before returning. This means the form/CRM that submitted the lead gets a real-time `WebhookResponse` with the AI score, priority tier, and a personalised next-step message. This enables immediate UX feedback to the submitter (e.g. "Our team will reach out within 2 hours") without any polling or separate status endpoint.

---

## AI Prompt Strategy

### Full system prompt

```
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
```

### Why JSON-only instruction
LLMs default to wrapping structured output in markdown code fences or prose explanations. The `CRITICAL: Return ONLY a raw JSON object` instruction, combined with explicit `json.loads()` mention, strongly conditions the model to produce machine-parseable output. A two-stage parser (direct `json.loads` → regex extraction) handles rare deviations.

### Why explicit schema in prompt
Defining every key name and value type directly in the prompt eliminates hallucinated field names (e.g. `"score"` instead of `"lead_score"`) and prevents the model from omitting optional but expected fields like `red_flags`. The schema acts as both an instruction and a contract.

### Why scoring tiers are defined with examples
Vague tier labels ("Hot", "Cold") are subjective. Anchoring each tier to observable signals (`budget signal`, `decision-maker title`, `urgency language`) aligns the model's scoring with actual B2B sales qualification criteria and produces consistent, explainable results across different lead types.

---

## Error Handling Strategy

| Failure Mode | Handling |
|---|---|
| `anthropic.APIError` | Caught, logged as `[AI_SCORER ERROR]`, returns `_FALLBACK` (`Manual Review`, score 0) |
| `anthropic.RateLimitError` | Caught before `APIError` (subclass), same fallback path |
| `asyncio.TimeoutError` | Caught, fallback used — pipeline never hangs |
| Malformed JSON response | Two-stage parse: `json.loads()` first, then `re.search(r'\{.*\}')` regex extraction; if both fail, fallback |
| Missing required fields | Caught in `validator.py` Step 1 before any API call; returns `(None, "missing_required_fields")` |
| Invalid email format | Regex validation in Step 3; returns `(None, "invalid_email_format")` |
| Low-context message | Length check `< 10 chars` in Step 4; returns `(None, "low_context_message")` |
| Google Sheets failure | Entire `write_to_sheets` wrapped in `try/except`; returns `False`, logs `[SHEETS ERROR]` — never crashes pipeline |
| Slack API failure | `SlackApiError` + `Exception` caught in `send_slack_notification`; returns `False`, logs `[SLACK ERROR]` |

The pipeline is designed so that **no single external dependency failure can prevent a `WebhookResponse` from being returned to the caller**.

---

## Bonus: Option C — Synchronous Webhook Response

The `/webhook/lead` endpoint uses FastAPI's native `async def` handler and `await`s the full pipeline:

```python
@app.post("/webhook/lead", response_model=WebhookResponse)
async def webhook_lead(lead: LeadInput) -> WebhookResponse:
    response = await run_pipeline(lead.model_dump())
    return response
```

This means:
- The HTTP connection stays open during AI processing (~1–3 seconds with Haiku)
- The caller receives a structured `WebhookResponse` with the score, tier, and a personalised `next_step` message in the same request
- A **Hot** lead gets: `"Our team will reach out within 2 hours. [personalised opener]"`
- A **Cold** lead gets: `"Thank you for reaching out. We'll review and follow up if there's a fit."`

No background jobs, no webhooks-on-webhooks, no polling endpoints required.

---

## Test Results

All 4 integration tests pass against the live server (`python -m pytest tests/ -v -s`):

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1

tests/test_pipeline.py::test_happy_path_high_intent_lead

  [TEST 1] Response: {
    "status": "qualified",
    "priority_tier": "Hot",
    "lead_score": 85,
    "next_step": "Our team will reach out within 2 hours. I saw you are looking
                  to automate onboarding at Example Corp."
  }
  PASSED

tests/test_pipeline.py::test_missing_message_field

  [TEST 2] Response: {
    "status": "rejected",
    "priority_tier": "Invalid",
    "lead_score": 0,
    "next_step": "Submission rejected: missing required fields."
  }
  PASSED

tests/test_pipeline.py::test_low_context_message

  [TEST 3] Response: {
    "status": "low_context",
    "priority_tier": "Cold",
    "lead_score": 5,
    "next_step": "Your message was too brief. We'll be in touch if we can help."
  }
  PASSED

tests/test_pipeline.py::test_spam_lead

  [TEST 4] Response: {
    "status": "qualified",
    "priority_tier": "Cold",
    "lead_score": 15,
    "next_step": "Thank you for reaching out. We'll review and follow up if there's a fit."
  }
  PASSED

========================== 4 passed in 10.83s ==============================
```

---

## Known Limitations

- **No deduplication** — the same lead can be submitted multiple times; each submission creates a new Sheets row and Slack notification with no cross-referencing.
- **No rate limiting** on the `/webhook/lead` endpoint — a malicious actor could flood the pipeline with requests, consuming Anthropic API tokens.
- **Google Sheets throughput** — the Sheets API enforces a ~100 requests/minute limit per project. High submission volumes would require batching writes or switching to BigQuery/a database.
- **Synchronous AI call** — the webhook holds the HTTP connection open during AI processing (~1–3s). Under high concurrency, this increases connection pool pressure on the ASGI server.
- **Service account credentials** stored as a local file (`credentials.json`) — in production, these should be injected via a secrets manager (AWS Secrets Manager, GCP Secret Manager, etc.).

---

## What I'd Improve With More Time

- **Vector similarity deduplication (Option A)** — embed each lead's company name + message using a sentence embedding model and store vectors in a lightweight vector DB (e.g. Qdrant or pgvector). Flag submissions from companies already in the pipeline to prevent duplicate Slack noise and wasted sales effort.

- **Redis queue for high-volume batching (Option B)** — move AI scoring off the request path. Acknowledge the webhook immediately (`202 Accepted`), enqueue the lead to Redis, and process with a Celery or `arq` worker pool. This decouples submission throughput from Anthropic API rate limits and enables retry logic with exponential backoff.

- **HubSpot / Pipedrive CRM integration** — after AI scoring, create or update a CRM contact via the HubSpot or Pipedrive REST API. Attach the `lead_score`, `priority_tier`, and `intent_summary` as custom properties, and auto-assign Hot leads to a sales rep via round-robin logic.

- **Prometheus metrics endpoint** — expose `/metrics` with counters for submissions by tier, error rates per module, and AI latency histograms. Feed into Grafana for real-time pipeline health monitoring.

- **Admin dashboard** — a lightweight read-only UI (Next.js or Streamlit) that reads from the Google Sheet and visualises lead volume, tier distribution, and red flag frequency over time.
