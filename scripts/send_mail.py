#!/usr/bin/env python3
"""Send an email via Gmail SMTP and log the event in the lead DB.

Usage:
    python3 scripts/send_mail.py <to_email> --subject "..." --body-file path/to/body.txt
    python3 scripts/send_mail.py <to_email> --subject "..." --body "inline body text"

The lead's stage stays at 'outreach' (already set when draft was created);
this script logs an 'email_sent' event with the timestamp.

Requires in .env:
    GMAIL_SMTP_USER=team@startupculture.co.in
    GMAIL_SMTP_PASSWORD=<16-char Google App Password>
"""

import argparse
import os
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

load_dotenv()

USER = os.getenv("GMAIL_SMTP_USER", "").strip()
PASS = os.getenv("GMAIL_SMTP_PASSWORD", "").strip().replace(" ", "")
FROM_DISPLAY = os.getenv("GMAIL_FROM_NAME", "Team Startup culture")
SLACK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()


def notify_slack(text: str) -> None:
    """Post a one-line confirmation to Slack. Fails silently."""
    if not SLACK_URL:
        return
    try:
        requests.post(SLACK_URL, json={"text": text}, timeout=8)
    except Exception:
        pass


def send_via_smtp(to_addr: str, subject: str, body: str) -> str:
    if not USER or not PASS:
        raise SystemExit("set GMAIL_SMTP_USER and GMAIL_SMTP_PASSWORD in .env")

    msg = MIMEMultipart()
    msg["From"] = f"{FROM_DISPLAY} <{USER}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
        smtp.login(USER, PASS)
        smtp.send_message(msg)
    return "sent"


def main():
    p = argparse.ArgumentParser(description="Send an email via Gmail SMTP")
    p.add_argument("to", help="recipient email address")
    p.add_argument("--subject", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--body", help="inline body text")
    g.add_argument("--body-file", help="path to a file containing the body")
    args = p.parse_args()

    body = args.body if args.body else Path(args.body_file).read_text(encoding="utf-8")

    print(f"sending to {args.to}...")
    status = send_via_smtp(args.to, args.subject, body)
    print(f"smtp: {status}")

    # log in DB if lead exists
    lead = db.get_lead_by_email(args.to)
    if lead:
        db.add_event(args.to, "email_sent",
                     f"sent via smtp script — subject: {args.subject[:80]}")
        print(f"db: event logged for lead id={lead['id']}")
        name = lead.get("name") or args.to
        company = lead.get("company") or "unknown company"
        notify_slack(
            f"*email sent ✓*\n"
            f"to: {name} ({company})\n"
            f"subject: {args.subject}\n"
            f"_watching for reply..._"
        )
        print("slack: notified")
    else:
        print(f"db: no lead found with email {args.to}, skipping event log")
        notify_slack(f"*email sent ✓*\nto: {args.to}\nsubject: {args.subject}")


if __name__ == "__main__":
    main()
