#!/usr/bin/env python3
"""Local Gmail reply watcher — runs every 5 minutes via launchd.

Reads outreach-stage leads from data/leads.db, polls Gmail via IMAP for new
replies from those leads since the last run, classifies each reply, updates
DB stages, and posts a Slack DM via SLACK_WEBHOOK_URL.

Requires in .env:
    GMAIL_SMTP_USER=team@startupculture.co.in
    GMAIL_SMTP_PASSWORD=<16-char Google App Password>
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
"""

import email
import imaplib
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

load_dotenv()

IMAP_USER = os.getenv("GMAIL_SMTP_USER", "").strip()
IMAP_PASS = os.getenv("GMAIL_SMTP_PASSWORD", "").strip().replace(" ", "")
SLACK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()
CALENDLY_TOKEN = os.getenv("CALENDLY_API_TOKEN", "").strip()
FIREFLIES_KEY = os.getenv("FIREFLIES_API_KEY", "").strip()

REPO_ROOT = Path(__file__).parent.parent
LAST_CHECK = REPO_ROOT / "data" / ".last_check.txt"
LOG_FILE = REPO_ROOT / "data" / ".gmail_check.log"
REMINDERS_SENT = REPO_ROOT / "data" / ".reminders_sent.json"
BOOKINGS_SEEN = REPO_ROOT / "data" / ".bookings_seen.json"
TRANSCRIPTS_SEEN = REPO_ROOT / "data" / ".transcripts_seen.json"

URGENT_KEYWORDS = ["today", "tonight", "this afternoon", "this evening",
                   "right now", "asap", "as soon as possible", "in an hour",
                   "in a couple hours", "today itself", "before eod"]
INTERESTED_KEYWORDS = ["yes", "let's talk", "lets talk", "send calendar",
                       "send the calendar", "send the link", "send me",
                       "happy to chat", "sounds good", "looks good",
                       "when can we", "let's chat", "lets chat"]
NOT_INTERESTED_KEYWORDS = ["no thanks", "not a fit", "not interested",
                           "remove me", "unsubscribe", "stop emailing"]
NEEDS_INFO_KEYWORDS = ["tell me more", "more info", "more information",
                       "how does it work", "what's the cost", "case study",
                       "case studies", "send case"]
AUTO_REPLY_KEYWORDS = ["out of office", "ooo", "automatic reply",
                       "auto-reply", "vacation"]


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")


def get_last_check() -> datetime:
    if LAST_CHECK.exists():
        try:
            return datetime.fromisoformat(LAST_CHECK.read_text().strip())
        except Exception:
            pass
    return datetime.now() - timedelta(minutes=10)


def set_last_check(ts: datetime) -> None:
    LAST_CHECK.parent.mkdir(parents=True, exist_ok=True)
    LAST_CHECK.write_text(ts.isoformat(timespec="seconds"))


def classify(body: str) -> str:
    b = body.lower()
    if any(k in b for k in AUTO_REPLY_KEYWORDS):
        return "AUTO_REPLY"
    if any(k in b for k in URGENT_KEYWORDS):
        return "URGENT_TODAY"
    if any(k in b for k in NOT_INTERESTED_KEYWORDS):
        return "NOT_INTERESTED"
    if any(k in b for k in NEEDS_INFO_KEYWORDS):
        return "NEEDS_INFO"
    if any(k in b for k in INTERESTED_KEYWORDS):
        return "INTERESTED"
    return "OTHER"


def get_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore"
                    )
                except Exception:
                    return ""
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="ignore"
            )
        except Exception:
            return ""
    return ""


def send_slack(text: str) -> None:
    if not SLACK_URL:
        log("no SLACK_WEBHOOK_URL set, skipping post")
        return
    try:
        requests.post(SLACK_URL, json={"text": text}, timeout=10)
    except Exception as exc:
        log(f"slack post failed: {exc}")


def check_replies():
    if not IMAP_USER or not IMAP_PASS:
        log("missing GMAIL_SMTP_USER or GMAIL_SMTP_PASSWORD")
        sys.exit(0)

    leads = db.list_leads(stage="outreach")
    lead_by_email = {l["email"].lower(): l for l in leads if l.get("email")}
    if not lead_by_email:
        log("no outreach-stage leads with email — nothing to check")
        return

    last = get_last_check()
    now = datetime.now()
    log(f"checking since {last.isoformat()}, {len(lead_by_email)} leads")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX")
    except Exception as exc:
        log(f"imap login failed: {exc}")
        return

    # IMAP SINCE only takes a date, not a datetime — we widen the search to
    # last day, then filter by exact timestamp
    since_str = (last - timedelta(days=1)).strftime("%d-%b-%Y")
    typ, data = mail.search(None, f'(SINCE "{since_str}")')
    if typ != "OK" or not data or not data[0]:
        log("imap search returned nothing")
        mail.close()
        mail.logout()
        set_last_check(now)
        return

    new_replies = []
    for num in data[0].split():
        typ, msg_data = mail.fetch(num, "(RFC822)")
        if typ != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])

        # Sender check
        from_addr = parseaddr(msg.get("From", ""))[1].lower()
        if from_addr not in lead_by_email:
            continue

        # Date check (exact)
        try:
            msg_dt = parsedate_to_datetime(msg.get("Date", ""))
            msg_dt = msg_dt.replace(tzinfo=None) if msg_dt.tzinfo else msg_dt
        except Exception:
            msg_dt = now
        if msg_dt < last:
            continue

        # Body + classification
        body = get_text_body(msg).strip()
        if not body:
            continue
        classification = classify(body)
        if classification in ("OTHER", "AUTO_REPLY"):
            continue

        lead = lead_by_email[from_addr]
        snippet = body.replace("\n", " ").strip()[:140]
        new_replies.append({
            "lead": lead,
            "classification": classification,
            "snippet": snippet,
            "msg_id": msg.get("Message-ID", "").strip(),
        })

    mail.close()
    mail.logout()

    if not new_replies:
        log("no new replies")
        set_last_check(now)
        return

    # Update DB + send Slack
    lines = [f"*sales pipeline — {len(new_replies)} new repl{'y' if len(new_replies) == 1 else 'ies'}*", ""]
    for r in new_replies:
        lead = r["lead"]
        cls = r["classification"]
        company = lead.get("company") or "unknown"
        name = lead["name"]

        # update DB stage to replied (if not already)
        if lead.get("stage") != "replied":
            db.update_lead(lead["email"], stage="replied",
                           next_step=f"reply ({cls.lower()}) — review and respond")

        # log event
        db.add_event(lead["email"], "reply",
                     f"{cls}: {r['snippet']}"[:500])

        # build slack line
        action_hint = {
            "URGENT_TODAY": "reply with same-day calendly slot",
            "INTERESTED": "send calendly link / book call",
            "NEEDS_INFO": "reply with case study or details",
            "NOT_INTERESTED": "mark lost",
        }.get(cls, "review and respond")

        lines.append(f"• {name} ({company}) — *{cls}*")
        lines.append(f"  > {r['snippet']}")
        lines.append(f"  next: {action_hint}")
        lines.append("")

    send_slack("\n".join(lines).strip())
    log(f"posted {len(new_replies)} replies to slack")
    set_last_check(now)


# ---------------------------------------------------------------------------
# Calendly: new bookings + 5-min reminders
# ---------------------------------------------------------------------------

def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def check_calendly():
    """Check Calendly for new bookings (since last run) + meetings starting
    in the next 4-10 minutes (one-shot 5-min reminders)."""
    if not CALENDLY_TOKEN:
        log("no CALENDLY_API_TOKEN, skipping Calendly check")
        return

    headers = {"Authorization": f"Bearer {CALENDLY_TOKEN}",
               "Content-Type": "application/json"}
    try:
        r = requests.get("https://api.calendly.com/users/me",
                         headers=headers, timeout=10)
        user_uri = r.json()["resource"]["uri"]
    except Exception as exc:
        log(f"calendly /users/me failed: {exc}")
        return

    now_utc = datetime.now(timezone.utc)
    params = {
        "user": user_uri,
        "min_start_time": now_utc.isoformat(),
        "max_start_time": (now_utc + timedelta(days=60)).isoformat(),
        "status": "active",
        "count": 50,
    }
    try:
        r = requests.get("https://api.calendly.com/scheduled_events",
                         headers=headers, params=params, timeout=10)
        events = r.json().get("collection", [])
    except Exception as exc:
        log(f"calendly events fetch failed: {exc}")
        return

    leads = db.list_leads()
    lead_by_email = {l["email"].lower(): l for l in leads if l.get("email")}

    bookings_seen = _load_state(BOOKINGS_SEEN)
    reminders_sent = _load_state(REMINDERS_SENT)
    new_bookings = []
    upcoming_reminders = []

    for ev in events:
        ev_uri = ev["uri"]
        try:
            r2 = requests.get(f"{ev_uri}/invitees", headers=headers, timeout=10)
            invitees = r2.json().get("collection", [])
        except Exception:
            continue

        for inv in invitees:
            inv_email = inv.get("email", "").lower()
            if inv_email not in lead_by_email:
                continue
            lead = lead_by_email[inv_email]

            start_time = datetime.fromisoformat(ev["start_time"].replace("Z", "+00:00"))
            join_url = ""
            loc = ev.get("location") or {}
            if isinstance(loc, dict):
                join_url = loc.get("join_url") or ""

            # NEW BOOKING detection: first time we've seen this event URI
            if ev_uri not in bookings_seen:
                new_bookings.append({
                    "lead": lead,
                    "start_time": start_time,
                    "join_url": join_url,
                    "ev_uri": ev_uri,
                })
                bookings_seen[ev_uri] = now_utc.isoformat()
                # Update DB stage
                if lead.get("stage") not in ("booked", "met", "won", "lost"):
                    db.update_lead(inv_email, stage="booked",
                                   next_step=f"prep for call at {start_time.astimezone().strftime('%Y-%m-%d %H:%M')}")
                    db.add_event(inv_email, "booking",
                                 f"calendly: {start_time.isoformat()} — {join_url}")

            # 5-MIN REMINDER detection: starts in 4-10 minutes
            time_until = (start_time - now_utc).total_seconds()
            if 240 <= time_until <= 600:  # between 4 and 10 minutes
                if ev_uri not in reminders_sent:
                    upcoming_reminders.append({
                        "lead": lead,
                        "start_time": start_time,
                        "join_url": join_url,
                        "minutes_until": int(time_until / 60),
                    })
                    reminders_sent[ev_uri] = now_utc.isoformat()

    # Slack notifications
    for b in new_bookings:
        lead = b["lead"]
        ist = b["start_time"].astimezone(timezone(timedelta(hours=5, minutes=30)))
        send_slack(
            f"*new booking ✓*\n"
            f"{lead['name']} ({lead.get('company') or 'unknown'}) booked a call\n"
            f"when: {ist.strftime('%a %d %b %Y at %H:%M IST')}\n"
            f"link: {b['join_url']}\n"
            f"next: prep talking points"
        )

    for r in upcoming_reminders:
        lead = r["lead"]
        ist = r["start_time"].astimezone(timezone(timedelta(hours=5, minutes=30)))
        send_slack(
            f"*heads up — meeting in {r['minutes_until']} min*\n"
            f"{lead['name']} ({lead.get('company') or 'unknown'})\n"
            f"when: {ist.strftime('%H:%M IST')}\n"
            f"join: {r['join_url']}"
        )

    # cleanup old state (events older than 7 days)
    cutoff = (now_utc - timedelta(days=7)).isoformat()
    bookings_seen = {k: v for k, v in bookings_seen.items() if v > cutoff}
    reminders_sent = {k: v for k, v in reminders_sent.items() if v > cutoff}
    _save_state(BOOKINGS_SEEN, bookings_seen)
    _save_state(REMINDERS_SENT, reminders_sent)

    if new_bookings or upcoming_reminders:
        log(f"calendly: {len(new_bookings)} new bookings, {len(upcoming_reminders)} reminders")
    else:
        log("calendly: no new bookings or upcoming meetings")


# ---------------------------------------------------------------------------
# Fireflies: meeting transcripts
# ---------------------------------------------------------------------------

def check_fireflies():
    """Pull recent Fireflies transcripts. For each transcript where a lead
    was a participant, post the summary to Slack and prompt for thank-you draft."""
    if not FIREFLIES_KEY:
        log("no FIREFLIES_API_KEY, skipping Fireflies check")
        return

    leads = db.list_leads()
    lead_emails = {l["email"].lower(): l for l in leads if l.get("email")}
    if not lead_emails:
        return

    headers = {"Authorization": f"Bearer {FIREFLIES_KEY}",
               "Content-Type": "application/json"}
    query = """
    query RecentTranscripts {
        transcripts(limit: 10) {
            id
            title
            date
            participants
            transcript_url
            summary {
                overview
                short_summary
                action_items
                keywords
            }
        }
    }
    """
    try:
        r = requests.post("https://api.fireflies.ai/graphql",
                          json={"query": query}, headers=headers, timeout=15)
        data = r.json()
    except Exception as exc:
        log(f"fireflies query failed: {exc}")
        return

    transcripts = (data.get("data") or {}).get("transcripts") or []
    if not transcripts:
        log("fireflies: no transcripts found")
        return

    seen = _load_state(TRANSCRIPTS_SEEN)
    cutoff_ms = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000

    for tr in transcripts:
        tr_id = tr.get("id")
        tr_date = tr.get("date")  # epoch ms
        if not tr_id or not tr_date or tr_date < cutoff_ms:
            continue
        if tr_id in seen:
            continue

        # Match participants against leads
        participants = [(p or "").lower() for p in (tr.get("participants") or [])]
        matched = [e for e in participants if e in lead_emails]
        if not matched:
            continue

        lead = lead_emails[matched[0]]
        summary = tr.get("summary") or {}
        overview = (summary.get("overview") or summary.get("short_summary") or "").strip()
        action_items = summary.get("action_items") or ""

        lines = [
            "*meeting notes ready*",
            f"{lead['name']} ({lead.get('company') or 'unknown'}) — {tr.get('title') or 'discovery call'}",
            "",
        ]
        if overview:
            lines.append(f"*summary:* {overview[:500]}")
            lines.append("")
        if action_items:
            lines.append(f"*action items:*\n{action_items[:600]}")
            lines.append("")
        lines.append(f"transcript: {tr.get('transcript_url') or '(none)'}")
        lines.append("next: i'll draft a thank-you email — tell me 'draft thanks for <name>' in chat")

        send_slack("\n".join(lines))
        db.add_event(lead["email"], "meeting",
                     f"fireflies transcript: {tr.get('title','')} — {overview[:200]}")
        if lead.get("stage") != "met":
            db.update_lead(lead["email"], stage="met",
                           next_step="send thank-you note + action items")

        seen[tr_id] = datetime.now(timezone.utc).isoformat()

    # cleanup state older than 14 days
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    seen = {k: v for k, v in seen.items() if v > cutoff_iso}
    _save_state(TRANSCRIPTS_SEEN, seen)
    log(f"fireflies: checked {len(transcripts)} transcripts")


if __name__ == "__main__":
    try:
        check_replies()
        check_calendly()
        check_fireflies()
    except Exception:
        log(f"unhandled error:\n{traceback.format_exc()}")
        sys.exit(0)  # don't crash launchd, fail silently
