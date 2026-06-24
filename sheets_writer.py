"""Handles writing lead data and scores to Google Sheets."""

import gspread

import config
from models import EnrichedLead

HEADERS = [
    "timestamp",
    "full_name",
    "email",
    "company_name",
    "job_title",
    "company_size",
    "budget_range",
    "message",
    "lead_score",
    "priority_tier",
    "intent_summary",
    "suggested_opener",
    "red_flags",
]


def write_to_sheets(lead: EnrichedLead) -> bool:
    try:
        # Step 1 — Authenticate using the service account JSON file
        client = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)

        # Step 2 — Open the spreadsheet by ID and select the first sheet
        spreadsheet = client.open_by_key(config.GOOGLE_SHEETS_ID)
        sheet = spreadsheet.get_worksheet(0)

        # Step 3 — Write header row if the sheet is empty (first run)
        first_row = sheet.row_values(1)
        if not first_row:
            sheet.append_row(HEADERS)

        # Step 4 — Build and append the data row in the same column order as HEADERS.
        # red_flags is a list, so convert it to a comma-separated string for the cell.
        row = [
            lead.timestamp,
            lead.full_name,
            lead.email,
            lead.company_name,
            lead.job_title,
            lead.company_size,
            lead.budget_range,
            lead.message,
            lead.lead_score,
            lead.priority_tier,
            lead.intent_summary,
            lead.suggested_opener,
            ", ".join(lead.red_flags),
        ]
        sheet.append_row(row)

        # Step 5 — Return True on success
        return True

    except Exception as e:
        # Step 6 — Log and swallow all errors so Sheets failure never crashes the pipeline
        print(f"[SHEETS ERROR] {e}")
        return False
