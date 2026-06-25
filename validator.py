"""Validation logic for incoming lead data."""

import re
from datetime import datetime, timezone
from models import NormalizedLead


def validate_and_normalize(data: dict) -> tuple[NormalizedLead | None, str | None]:
    # Step 1 — Required field check:
    # Ensure full_name, email, and message are present and not empty after stripping whitespace.
    full_name_raw = str(data.get("full_name", ""))
    email_raw = str(data.get("email", ""))
    message_raw = str(data.get("message", ""))
    
    if not full_name_raw.strip() or not email_raw.strip() or not message_raw.strip():
        return (None, "missing_required_fields")

    # Step 2 — Normalize all string fields:
    # Strip whitespace from every known field.
    # Lowercase the email to ensure consistent comparison and storage.
    normalized_data = {}
    for field in ["full_name", "email", "company_name", "job_title", "phone", "company_size", "budget_range", "message"]:
        val = data.get(field, "")
        normalized_data[field] = str(val).strip() if val is not None else ""
        
    normalized_data["email"] = normalized_data["email"].lower()
    
    # If any optional field is completely empty, we provide a placeholder to ensure non-empty strings.
    # We do this because models.py expects all fields in NormalizedLead to be non-empty strings.
    for field in ["company_name", "job_title", "phone", "company_size", "budget_range"]:
        if not normalized_data[field]:
            normalized_data[field] = "N/A"

    # Step 3 — Email format validation:
    # Verify the email matches a basic structure (local-part@domain.tld) to catch obvious typos.
    email_regex = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
    if not re.match(email_regex, normalized_data["email"]):
        return (None, "invalid_email_format")

    # Step 4 — Message length check:
    # Ensure the message has enough characters (>= 10) to provide context for AI scoring.
    if len(normalized_data["message"]) < 10:
        return (None, "low_context_message")

    # Step 5 — All checks passed:
    # Build and return the NormalizedLead with a UTC ISO 8601 timestamp.
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        lead = NormalizedLead(**normalized_data, timestamp=timestamp)
        return (lead, None)
    except Exception as e:
        # Never raise exceptions, return a tuple indicating failure
        return (None, f"model_validation_failed: {str(e)}")
