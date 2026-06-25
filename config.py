"""Configuration settings and environment variable loading."""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Return an env var or raise ValueError if missing."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str:
    """Return an env var or empty string if not set."""
    return os.getenv(name, "")


# ── Required: integrations that must always be configured ──────────────
GOOGLE_SHEETS_ID = _require("GOOGLE_SHEETS_ID")
GOOGLE_CREDENTIALS_PATH = _require("GOOGLE_CREDENTIALS_PATH")
SLACK_BOT_TOKEN = _require("SLACK_BOT_TOKEN")
SLACK_HOT_CHANNEL = _require("SLACK_HOT_CHANNEL")
SLACK_GENERAL_CHANNEL = _require("SLACK_GENERAL_CHANNEL")

# ── Optional: at least one AI provider key should be present ───────────
GEMINI_API_KEY = _optional("GEMINI_API_KEY")
GITHUB_TOKEN = _optional("GITHUB_TOKEN")
ANTHROPIC_API_KEY = _optional("ANTHROPIC_API_KEY")

if not any([GEMINI_API_KEY, GITHUB_TOKEN, ANTHROPIC_API_KEY]):
    raise ValueError(
        "At least one AI provider key must be set: "
        "GEMINI_API_KEY, GITHUB_TOKEN, or ANTHROPIC_API_KEY"
    )

# ── Pipeline settings ─────────────────────────────────────────────────
WEBHOOK_TIMEOUT_SECONDS = 12   # AI must respond within this time
APP_VERSION = "1.0.0"
