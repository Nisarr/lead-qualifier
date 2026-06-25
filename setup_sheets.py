import sys
sys.stdout.reconfigure(encoding='utf-8')

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
gc = gspread.authorize(creds)

SHEET_ID = "1F9wUP6GoKNsfycr1ri7TN2o5aTUC5AJWGQcYToap95U"
SERVICE_EMAIL = "lead-qualifier@lead-qualifier-500409.iam.gserviceaccount.com"

try:
    sh = gc.open_by_key(SHEET_ID)
    print(f"[OK] Successfully opened sheet: {sh.title}")

    # Ensure headers exist
    ws = sh.sheet1
    existing = ws.row_values(1)
    if not existing:
        headers = [
            "Timestamp", "Full Name", "Email", "Company", "Job Title",
            "Company Size", "Budget", "Lead Score", "Priority Tier",
            "Intent Summary", "Red Flags", "Next Step"
        ]
        ws.append_row(headers)
        print("[OK] Added headers to Sheet1")
    else:
        print(f"[OK] Sheet already has headers: {existing[:3]}...")

except gspread.exceptions.SpreadsheetNotFound:
    print("[ERROR] Sheet not found. You need to share the sheet with the service account.")
    print(f"        Share with: {SERVICE_EMAIL}")
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    if "PERMISSION_DENIED" in str(e) or "403" in str(e):
        print(f"\n[ACTION NEEDED] Share the Google Sheet with Editor access to:")
        print(f"  {SERVICE_EMAIL}")
        print(f"\n  Steps:")
        print(f"  1. Open: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
        print(f"  2. Click Share button (top right)")
        print(f"  3. Paste: {SERVICE_EMAIL}")
        print(f"  4. Set to Editor -> Send")
