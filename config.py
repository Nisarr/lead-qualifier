"""Configuration settings and environment variable loading."""

import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value

ANTHROPIC_API_KEY = get_env_var("ANTHROPIC_API_KEY")
GOOGLE_SHEETS_ID = get_env_var("GOOGLE_SHEETS_ID")
GOOGLE_CREDENTIALS_PATH = get_env_var("GOOGLE_CREDENTIALS_PATH")
SLACK_BOT_TOKEN = get_env_var("SLACK_BOT_TOKEN")
SLACK_HOT_CHANNEL = get_env_var("SLACK_HOT_CHANNEL")
SLACK_GENERAL_CHANNEL = get_env_var("SLACK_GENERAL_CHANNEL")
