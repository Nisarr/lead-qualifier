"""Sends notifications about leads to Slack channels."""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import config
from models import EnrichedLead


def send_slack_notification(lead: EnrichedLead) -> bool:
    try:
        # Step 1 — Initialize the Slack WebClient with the bot token
        client = WebClient(token=config.SLACK_BOT_TOKEN)

        # Step 2 — Route to the correct channel based on priority tier
        if lead.priority_tier == "Hot":
            channel = config.SLACK_HOT_CHANNEL
        else:
            # Warm, Cold, and Manual Review all go to the general channel
            channel = config.SLACK_GENERAL_CHANNEL

        # Step 3 — Build the Slack Block Kit message

        # Block 1 — Header: tier-specific emoji and label
        tier_headers = {
            "Hot": "🔥 HOT LEAD — Action Required @channel",
            "Warm": "🌡️ WARM LEAD",
            "Cold": "❄️ COLD LEAD",
            "Manual Review": "⚠️ MANUAL REVIEW NEEDED",
        }
        header_text = tier_headers.get(lead.priority_tier, "📋 NEW LEAD")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": header_text, "emoji": True},
            },
            # Block 2 — Lead Info: key fields in a compact section
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Name:* {lead.full_name} | *Company:* {lead.company_name}\n"
                        f"*Title:* {lead.job_title} | *Budget:* {lead.budget_range}\n"
                        f"*Score:* {lead.lead_score}/100 | *Tier:* {lead.priority_tier}"
                    ),
                },
            },
            # Block 3 — Intent summary
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Intent:* {lead.intent_summary}",
                },
            },
        ]

        # Block 4 — Suggested opener (only included when non-empty)
        if lead.suggested_opener:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Suggested Opener:* {lead.suggested_opener}",
                    },
                }
            )

        # Block 5 — Red flags (only included when the list is non-empty)
        if lead.red_flags:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚠️ Red Flags:* {', '.join(lead.red_flags)}",
                    },
                }
            )

        # Step 4 — Post the message to the chosen channel
        client.chat_postMessage(channel=channel, blocks=blocks)

        # Step 5 — Return True on success
        return True

    except SlackApiError as e:
        print(f"[SLACK ERROR] {e}")
        return False
    except Exception as e:
        print(f"[SLACK ERROR] {e}")
        return False
