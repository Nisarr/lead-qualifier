"""Create the Slack channels used by the lead qualifier pipeline.

Run once during initial setup:
    python create_channels.py
"""

import sys

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

load_dotenv()

import config  # noqa: E402
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

client = WebClient(token=config.SLACK_BOT_TOKEN)

channels_to_create = ["hot-leads", "leads-incoming"]

for channel_name in channels_to_create:
    try:
        response = client.conversations_create(name=channel_name)
        print(f"[OK] Created channel: #{channel_name} (ID: {response['channel']['id']})")
    except SlackApiError as e:
        error = e.response["error"]
        if error == "name_taken":
            print(f"[SKIP] Channel #{channel_name} already exists.")
        elif error == "missing_scope":
            needed = e.response.get("needed", "")
            provided = e.response.get("provided", "")
            print(f"[ERROR] Missing scope. Needed: {needed} | Provided: {provided}")
            print("        --> You need to reinstall the app after adding the scope.")
            print("        --> Go to api.slack.com/apps -> Your App -> OAuth & Permissions -> Reinstall to Workspace")
        else:
            print(f"[ERROR] #{channel_name}: {error}")

print("\nDone.")
