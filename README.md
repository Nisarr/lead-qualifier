# Lead Qualification Automation — Technical Assessment

A FastAPI-based B2B lead qualification system that validates, AI-scores, logs, and notifies on inbound sales leads in real-time. Implements **all three** bonus extensions: vector memory deduplication, batch processing, and synchronous webhook response.

---

## Architecture Overview

Every lead submission flows through a strict pipeline before a response is returned to the caller:

```
                         ┌──────────────────────────────────────────────────────────┐
  Webhook Caller         │                Lead Qualifier Pipeline                    │
  ─────────────          │                                                           │
                         │  1. TRIGGER       2. FILTER        3. AI                 │
  POST /webhook/lead ───►│  ───────────      ────────         ────────              │
                         │  Receive raw  → Validate &  →  Vector Memory  →         │
                         │  JSON payload    normalize      similarity check         │
                         │                  (reject bad         │                    │
                         │                   inputs)      Multi-provider            │
                         │                                AI fallback chain         │
                         │                                scores the lead           │
                         │                                      │                    │
                         │                          4. OUTPUT    ▼                   │
                         │                          ─────────────                    │
                         │                        ┌──────────────────┐              │
                         │                        │  Google Sheets   │              │
                         │                        │  (append row)    │              │
                         │                        └──────────────────┘              │
                         │                        ┌──────────────────┐              │
                         │                        │  Slack Notify    │              │
                         │                        │  (Block Kit msg) │              │
                         │                        └──────────────────┘              │
                         │                        ┌──────────────────┐              │
                         │                        │  Vector Memory   │              │
                         │                        │  (store embed)   │              │
                         │                        └──────────────────┘              │
                         │                                      │                    │
  ◄── WebhookResponse ──│◄──────────────────────────────────────                    │
  (real-time JSON with   └──────────────────────────────────────────────────────────┘
   request_id, score,
   tier, response_time)

  POST /webhook/batch ───► Same pipeline × N leads → single Slack summary
  POST /webhook/batch/csv  (CSV upload variant)
```

**Validation failures** (missing fields, bad email, too-short message) are short-circuited before any AI call, saving tokens and cost. All submission types — including rejected and low-context leads — are logged to Google Sheets for a complete audit trail.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| API Framework | **FastAPI** 0.128+ with `uvicorn` ASGI server |
| Language | **Python 3.11+** (compatible with 3.13) |
| AI Scoring | **Multi-provider chain**: Gemini 2.0 Flash Lite → GitHub Models GPT-4o-mini → Anthropic Claude Haiku |
| Data Validation | **Pydantic v2** with strict field constraints |
| Lead Logging | **Google Sheets API** via `gspread` + service account auth |
| Notifications | **Slack SDK** (`slack-sdk`) with Block Kit messages |
| Vector Memory | **sentence-transformers** (`all-MiniLM-L6-v2`) + SQLite + cosine similarity via `scikit-learn` |
| Config | `python-dotenv` for environment variable management |
| HTTP Client | `httpx` (async-capable, used in tests) |
| Testing | `pytest` with 8 core tests + standalone bonus feature tests |

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
# Required
GOOGLE_SHEETS_ID=your-sheet-id
GOOGLE_CREDENTIALS_PATH=credentials.json
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_HOT_CHANNEL=#hot-leads
SLACK_GENERAL_CHANNEL=#leads-incoming

# AI Providers — at least one must be set
GEMINI_API_KEY=your-gemini-key
GITHUB_TOKEN=your-github-pat
ANTHROPIC_API_KEY=sk-ant-...
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

Open the contact form at `http://localhost:8000/` in your browser.

### 7. Run tests

```bash
# Core pipeline tests (requires server running)
python -m pytest tests/test_pipeline.py -v -s

# Bonus feature tests (requires server running)
python tests/test_integration.py
python tests/test_vector_memory.py
python tests/test_batch.py
python tests/test_webhook_response.py
```

---

## Key Design Decisions

### Validation before AI (token efficiency & cost)
The `validate_and_normalize` step runs entirely locally with zero API calls. Leads with missing required fields, invalid email formats, or messages shorter than 10 characters are rejected or flagged before any AI provider is called. This eliminates unnecessary token spend on obviously invalid submissions and keeps latency low.

### Multi-provider AI fallback chain
Rather than depending on a single AI provider, the scorer implements a three-deep fallback chain: **Gemini 2.0 Flash Lite → GitHub Models (GPT-4o-mini) → Anthropic Claude Haiku**. Each provider has an independent 15-second timeout. If all three fail, a static `"Manual Review"` fallback is returned. This design ensures the pipeline never crashes due to a single provider outage.

### Temperature = 0.1 (consistent, repeatable scoring)
Lead scoring must be deterministic across similar inputs. A temperature near 0 minimises token sampling randomness, ensuring the same lead profile receives a similar score on repeat calls. This is important for auditability and for the Sheets log to be trustworthy over time.

### System prompt separated from lead data
The `LEAD_SCORING_SYSTEM_PROMPT` is a module-level constant passed as the `system` parameter, not injected into the user message. This leverages the provider's native system prompt handling, keeps the user message lean (only the 5 fields the model needs for scoring), and maintains a clean separation between instructions and data.

### Token efficiency — selective field forwarding
Only 5 fields are sent to the AI: `company_name`, `job_title`, `company_size`, `budget_range`, and `message`. Fields like `email`, `phone`, and `full_name` are irrelevant to scoring and are excluded from the prompt, reducing token usage by ~30%.

### Complete audit trail in Google Sheets
All submission types — including rejected, low-context, and error leads — are written to Google Sheets. This ensures the spreadsheet serves as a complete audit trail for every form submission, not just the ones that passed AI scoring.

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
| AI provider error / timeout | Each provider wrapped in `try/except` with 15s `asyncio.wait_for` timeout; next provider in chain is attempted; static fallback if all fail |
| Pipeline-level timeout | `asyncio.wait_for` wraps the entire AI call with a 12s limit; if exceeded, the lead is routed to "Manual Review" with `ai_timeout` red flag |
| Malformed JSON response | Two-stage parse: `json.loads()` first, then `re.search(r'\{.*\}')` regex extraction; Pydantic `ValidationError` caught; fallback if both fail |
| Missing required fields | Caught in `validator.py` Step 1 before any API call; logged to Sheets and Slack |
| Invalid email format | Regex validation in Step 3; logged to Sheets; rejected silently |
| Low-context message | Length check `< 10 chars` in Step 4; logged to Sheets; lightweight Slack notification sent |
| Google Sheets failure | Entire `write_to_sheets` wrapped in `try/except`; returns `False`, logs `[SHEETS ERROR]` — never crashes pipeline |
| Slack API failure | `SlackApiError` + `Exception` caught in `send_slack_notification`; returns `False`, logs `[SLACK ERROR]` |
| Unexpected error codes | Catch-all handler in pipeline routes unknown errors to "Manual Review" with Sheets logging |

The pipeline is designed so that **no single external dependency failure can prevent a `WebhookResponse` from being returned to the caller**.

---

## Bonus: Option A — Memory / Vector Lookup

Before scoring a new lead, the pipeline queries a **local vector database** to check if a similar inquiry has been seen before.

### How it works

1. **Embedding**: Each lead's company name, job title, and message are concatenated and embedded using the `all-MiniLM-L6-v2` sentence-transformer model (~22M parameters, runs locally, no API key needed).

2. **Storage**: Embeddings are stored as JSON arrays in a SQLite database (`lead_memory.db`), along with metadata (company name, email domain, message preview, lead score, priority tier, timestamp).

3. **Similarity search**: On each new lead, cosine similarity is computed against all stored embeddings. If the best match exceeds a `0.82` similarity threshold, the match metadata is returned.

4. **AI context injection**: When a match is found, prior context is appended to the AI prompt:
   ```
   ⚠️ MEMORY CONTEXT — Similar inquiry detected:
   Prior company: Acme Corp
   Prior qualification: Hot (score: 92)
   Similarity: 0.891
   Prior message preview: We are looking for an AI-powered lead...
   ```
   The AI factors this into its analysis and the pipeline appends a `"returning inquiry"` red flag.

5. **Singleton pattern**: The `VectorMemory` class uses a thread-safe singleton so the ~90MB model is loaded once at startup, not on every request.

### Implementation files
- `vector_memory.py` — `VectorMemory` class with `find_similar()` and `store_lead()` methods
- `pipeline.py` — Lines 118-145: memory lookup before AI scoring, storage after scoring
- `ai_scorer.py` — Lines 153-165: prior context injection into the AI prompt

---

## Bonus: Option B — Batch / Loop Processing

A secondary path accepts a batch of leads at once (JSON array or CSV upload), processes each through the full pipeline with rate-limited concurrency, and sends a single consolidated Slack summary.

### Endpoints

| Method | Path | Content Type | Description |
|---|---|---|---|
| `POST` | `/webhook/batch` | `application/json` | JSON body: `{"leads": [...]}` with up to 50 LeadInput dicts |
| `POST` | `/webhook/batch/csv` | `multipart/form-data` | CSV upload; column headers must match LeadInput fields |

### How it works

1. **Concurrency control**: Leads are processed concurrently using `asyncio.gather`, but an `asyncio.Semaphore(3)` caps simultaneous AI calls to 3. A `0.5s` delay is injected after each AI call to stay under provider rate limits.

2. **Per-lead pipeline reuse**: Each lead in the batch runs through the exact same `run_pipeline()` function as single leads — validation, AI scoring, Sheets logging, and individual Slack notifications all apply.

3. **Aggregated response**: The batch endpoint returns a single JSON response with counts by tier, total processed/rejected, and per-lead results:
   ```json
   {
     "status": "batch_complete",
     "total": 5,
     "processed": 3,
     "rejected": 2,
     "breakdown": {"hot": 1, "warm": 1, "cold": 1, "manual_review": 0},
     "results": [...]
   }
   ```

4. **Consolidated Slack summary**: After all leads are processed, a single summary message is posted to the general Slack channel listing counts by tier and calling out hot leads by name for immediate action.

5. **CSV parsing**: The `parse_csv()` helper uses Python's `csv.DictReader`, strips whitespace from all fields, and silently skips blank rows.

### Implementation files
- `batch_processor.py` — `process_batch()` (async runner with semaphore), `parse_csv()`, `BatchResult` dataclass
- `main.py` — `/webhook/batch` and `/webhook/batch/csv` route handlers
- `notifier.py` — `send_batch_summary()` function

---

## Bonus: Option C — Synchronous Webhook Response

The `/webhook/lead` endpoint returns a **real-time JSON response** containing the AI score, priority tier, and a personalised next-step message — all computed synchronously before the HTTP response is sent.

### Enhanced `WebhookResponse` schema

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "qualified",
  "priority_tier": "Hot",
  "lead_score": 87,
  "next_step": "Hi Jordan, thank you for reaching out to us. Based on what you've shared, we can definitely help. We'd love to schedule a demo to show how our AI qualification engine can integrate with your existing sales tools. Expect a call from our team within 2 hours.",
  "response_time_ms": 2341,
  "version": "1.0.0"
}
```

### Key enhancements

- **`request_id`** (UUID): Unique per submission, for tracking and support reference. Also set as `X-Request-ID` response header.
- **`response_time_ms`**: Server-side elapsed time in milliseconds. Also set as `X-Response-Time-Ms` response header.
- **`version`**: API version string for client compatibility.
- **`X-Priority-Tier` header**: Allows the caller to route based on headers without parsing the JSON body.
- **Personalised `next_step`**: Uses the lead's first name and tier to construct a tailored message. Hot leads get the AI's `suggested_opener` woven into the response.
- **Timeout protection**: If the AI doesn't respond within 12 seconds, the pipeline returns a `"timeout"` status with a "Manual Review" tier, so the caller always gets a response.

### Implementation files
- `pipeline.py` — Lines 53-167: full pipeline with timing, UUID generation, timeout handling, personalised next-step builder
- `main.py` — Lines 47-61: webhook handler with custom response headers
- `models.py` — `WebhookResponse` with enhanced fields

---

## Test Results

All tests pass against the live server:

### Core pipeline tests (`test_pipeline.py`)

| # | Test Case | Expected Outcome |
|---|-----------|-----------------:|
| 1 | Happy path — high-intent lead | `status=qualified`, tier=Hot/Warm, score > 40 |
| 2 | Empty message string | `status=rejected` |
| 3 | Message key omitted entirely | `status=rejected` (not 422) |
| 4 | Low-context message ("hi") | `status=low_context`, tier=Cold, score=5 |
| 5 | Spam lead | tier=Cold, score < 40 |
| 6 | Invalid email format | `status=rejected`, mentions "email" |
| 7 | Missing full_name | `status=rejected` |
| 8 | Health check | `status=ok` |

### Bonus feature tests (`test_integration.py`)

| # | Test Area | Checks |
|---|-----------|--------|
| 1 | Enhanced webhook response | `request_id` is UUID, `response_time_ms > 0`, `version=1.0.0`, personalised `next_step`, custom response headers |
| 2 | Vector memory detection | Second lead from same company triggers memory match; SQLite stores 2 embeddings |
| 3 | Batch processing | 5-lead batch → `batch_complete` status, tier breakdown sums, per-result `tier` and `score` fields |

---

## Known Limitations

- **No rate limiting** on the `/webhook/lead` endpoint — a malicious actor could flood the pipeline with requests, consuming AI provider tokens.
- **Google Sheets throughput** — the Sheets API enforces a ~100 requests/minute limit per project. High submission volumes would require batching writes or switching to BigQuery/a database.
- **Synchronous AI call** — the webhook holds the HTTP connection open during AI processing (~1–3s). Under high concurrency, this increases connection pool pressure on the ASGI server.
- **Service account credentials** stored as a local file (`credentials.json`) — in production, these should be injected via a secrets manager.
- **Vector memory scales linearly** — cosine similarity is computed against all stored embeddings. Beyond ~10k leads, an approximate nearest-neighbour index (FAISS, pgvector) would be needed.

---

## What I'd Improve With More Time

- **CRM integration** — after AI scoring, create or update a CRM contact via the HubSpot or Pipedrive REST API. Attach the `lead_score`, `priority_tier`, and `intent_summary` as custom properties, and auto-assign Hot leads to a sales rep via round-robin logic.

- **Prometheus metrics endpoint** — expose `/metrics` with counters for submissions by tier, error rates per module, and AI latency histograms. Feed into Grafana for real-time pipeline health monitoring.

- **Admin dashboard** — a lightweight read-only UI (Next.js or Streamlit) that reads from the Google Sheet and visualises lead volume, tier distribution, and red flag frequency over time.

- **FAISS vector index** — replace the brute-force cosine similarity with a FAISS `IndexFlatIP` for sub-millisecond similarity search at scale, supporting 100k+ stored leads.

- **Redis queue for ultra-high-volume** — move AI scoring off the request path with `202 Accepted`, enqueue to Redis, and process with an `arq` worker pool for true horizontal scaling.
