#!/usr/bin/env python3
"""Freshworks CRM sync — pushes leads from data/leads.db into Freshworks
and supports targeted stage updates after events (email sent, reply, booking).

Usage:
    python3 scripts/freshworks_sync.py                      # full sync from leads.db
    python3 scripts/freshworks_sync.py --test               # test connection
    python3 scripts/freshworks_sync.py --dry-run            # preview, no API calls
    python3 scripts/freshworks_sync.py --update <email> <stage>
                                                            # update one lead's stage
                                                            # stage: outreach | replied | interested |
                                                            #        booked | met | won | lost

.env:
    FRESHWORKS_DOMAIN=startupculture-org
    FRESHWORKS_API_KEY=your_api_key
"""

import hashlib
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

load_dotenv()

DOMAIN = os.getenv("FRESHWORKS_DOMAIN", "").strip().rstrip("/")
API_KEY = os.getenv("FRESHWORKS_API_KEY", "").strip()

if not DOMAIN or not API_KEY:
    raise SystemExit("Set FRESHWORKS_DOMAIN and FRESHWORKS_API_KEY in .env")

BASE_URL = f"https://{DOMAIN}.myfreshworks.com/crm/sales/api"
HEADERS = {
    "Authorization": f"Token token={API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# pipeline stage → Freshworks tag (so you can filter by stage in CRM)
STAGE_TAGS = {
    "scouted": "stage:scouted",
    "qualified": "stage:qualified",
    "outreach": "stage:outreach",
    "replied": "stage:replied",
    "interested": "stage:interested",
    "follow-up": "stage:follow-up",
    "booked": "stage:booked",
    "met": "stage:met",
    "won": "stage:won",
    "lost": "stage:lost",
}


# ---------------------------------------------------------------------------
# Lead loader (reads from data/leads.db)
# ---------------------------------------------------------------------------

def _placeholder_phone(seed: str) -> str:
    """Deterministic placeholder for leads without a real phone."""
    import re
    h = hashlib.md5((seed or "lead").encode()).hexdigest()
    digits = re.sub(r"\D", "", h)[:10].ljust(10, "0")
    return f"+1{digits}"


def load_leads() -> list[dict]:
    """Read all leads from the SQLite DB and shape them for the sync flow."""
    rows = db.list_leads()
    leads = []
    for r in rows:
        phone = r.get("phone") or ""
        is_placeholder = False
        if not phone:
            phone = _placeholder_phone(r.get("email") or r["name"])
            is_placeholder = True
        leads.append({
            "name": r["name"],
            "company": r.get("company") or "",
            "role": r.get("role") or "",
            "email": r.get("email") or "",
            "phone": phone,
            "phone_is_placeholder": is_placeholder,
            "linkedin": r.get("linkedin") or "",
            "stage_raw": (r.get("stage") or "scouted").lower(),
            "next_step": r.get("next_step") or "",
            "notes": r.get("notes") or "",
            "source": r.get("source") or "",
            "verification": r.get("verification_status") or "",
        })
    return leads


# ---------------------------------------------------------------------------
# Freshworks API
# ---------------------------------------------------------------------------

def find_contact_by_email(email: str) -> dict | None:
    if not email:
        return None
    r = requests.get(
        f"{BASE_URL}/lookup",
        headers=HEADERS,
        params={"q": email, "f": "email", "entities": "contact"},
        timeout=10,
    )
    if r.status_code != 200:
        return None
    contacts = r.json().get("contacts", {}).get("contacts") or []
    return contacts[0] if contacts else None


def _build_payload(lead: dict, existing_tags: list[str] | None = None) -> dict:
    name_parts = lead["name"].split(" ", 1)
    first = name_parts[0]
    last = name_parts[1] if len(name_parts) > 1 else "—"

    placeholder_note = ""
    if lead.get("phone_is_placeholder"):
        placeholder_note = "\n[NOTE: phone is a placeholder — update with real number]"

    description = (
        f"Stage: {lead['stage_raw']}\n"
        f"Next step: {lead['next_step']}\n"
        f"Source: {lead['source']}\n"
        f"Verification: {lead['verification']}\n"
        f"LinkedIn: {lead['linkedin']}{placeholder_note}\n\n"
        f"{lead['notes']}"
    )

    # rebuild tag list — drop any old stage:* tags, add the current one
    tags = [t for t in (existing_tags or []) if not t.startswith("stage:")]
    stage_tag = STAGE_TAGS.get(lead["stage_raw"])
    if stage_tag:
        tags.append(stage_tag)

    payload = {
        "contact": {
            "first_name": first,
            "last_name": last,
            "job_title": lead["role"] or None,
            "email": lead["email"] or None,
            "mobile_number": lead["phone"],
            "description": description,
            "tags": tags,
        }
    }
    if lead["company"]:
        payload["contact"]["sales_account"] = {"name": lead["company"]}
    return payload


def create_or_update(lead: dict) -> tuple[str, str]:
    """Returns (status, detail). status: 'created' | 'updated' | 'failed'."""
    existing = find_contact_by_email(lead["email"]) if lead["email"] else None

    if existing:
        cid = existing["id"]
        existing_tags = [t["name"] for t in existing.get("tags", []) if isinstance(t, dict)]
        payload = _build_payload(lead, existing_tags)
        r = requests.put(f"{BASE_URL}/contacts/{cid}", headers=HEADERS, json=payload, timeout=15)
        if r.status_code in (200, 201):
            return "updated", str(cid)
        return "failed", f"PUT {r.status_code}: {r.text[:150]}"

    payload = _build_payload(lead)
    r = requests.post(f"{BASE_URL}/contacts", headers=HEADERS, json=payload, timeout=15)
    if r.status_code in (200, 201):
        return "created", str(r.json().get("contact", {}).get("id", ""))
    return "failed", f"POST {r.status_code}: {r.text[:150]}"


def update_stage(email: str, stage: str) -> None:
    """Update a single lead's stage tag in Freshworks (called after an event)."""
    stage = stage.lower()
    if stage not in STAGE_TAGS:
        raise SystemExit(f"unknown stage '{stage}'. valid: {', '.join(STAGE_TAGS)}")

    contact = find_contact_by_email(email)
    if not contact:
        print(f"no contact found for {email}")
        return

    cid = contact["id"]
    existing_tags = [t["name"] for t in contact.get("tags", []) if isinstance(t, dict)]
    new_tags = [t for t in existing_tags if not t.startswith("stage:")] + [STAGE_TAGS[stage]]

    payload = {
        "contact": {
            "tags": new_tags,
            "description": (contact.get("description") or "")
            + f"\n\n[{stage} → updated via sync]",
        }
    }
    r = requests.put(f"{BASE_URL}/contacts/{cid}", headers=HEADERS, json=payload, timeout=15)
    if r.status_code in (200, 201):
        print(f"updated {email} → stage:{stage}")
    else:
        print(f"failed {email}: {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------------------
# Connection test / dry-run / main sync
# ---------------------------------------------------------------------------

def test_connection() -> bool:
    print(f"  domain: {DOMAIN}.myfreshworks.com")
    print(f"  key:    {API_KEY[:6]}...{API_KEY[-4:]} ({len(API_KEY)} chars)")
    r = requests.post(f"{BASE_URL}/contacts", headers=HEADERS, json={"contact": {}}, timeout=10)
    if r.status_code == 400:
        print("  contacts write access: ok")
        return True
    print(f"  FAIL — {r.status_code}: {r.text[:200]}")
    return False


def sync(leads: list[dict]) -> None:
    counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    for lead in leads:
        name = lead["name"]
        stage = lead["stage_raw"]

        if "lost" in stage or "disqualified" in stage:
            print(f"  skip   {name} ({stage})")
            counts["skipped"] += 1
            continue
        if not lead["email"]:
            print(f"  skip   {name} — no email")
            counts["skipped"] += 1
            continue

        result, detail = create_or_update(lead)
        marker = {"created": "create", "updated": "update", "failed": "ERROR "}[result]
        ph = " (placeholder phone)" if lead["phone_is_placeholder"] else ""
        print(f"  {marker} {name:<28} <{lead['email']}> [{stage}]{ph}")
        if result == "failed":
            print(f"          → {detail}")
        counts[result] += 1

    print(f"\ndone — created: {counts['created']}  updated: {counts['updated']}  skipped: {counts['skipped']}  failed: {counts['failed']}")
    if counts["created"] or counts["updated"]:
        print(f"\nView in Freshworks: https://{DOMAIN}.myfreshworks.com/crm/sales/contacts")


def dry_run(leads: list[dict]) -> None:
    print("preview of leads that would be synced:\n")
    for l in leads:
        stage = l["stage_raw"]
        skip = ""
        if "lost" in stage or "disqualified" in stage:
            skip = "[skip: disqualified]"
        elif not l["email"]:
            skip = "[skip: no email]"
        marker = "  " if skip else "→ "
        ph = " *placeholder phone*" if l["phone_is_placeholder"] else ""
        print(f"  {marker}{l['name']:<28} | {l['email'] or '—':<35} | {stage:<10} {skip}{ph}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--test" in args:
        print("testing freshworks connection...")
        sys.exit(0 if test_connection() else 1)

    if "--update" in args:
        i = args.index("--update")
        if i + 2 >= len(args):
            raise SystemExit("usage: --update <email> <stage>")
        update_stage(args[i + 1], args[i + 2])
        sys.exit(0)

    print(f"reading {db.DB_PATH}")
    leads = load_leads()
    print(f"found {len(leads)} leads\n")

    if "--dry-run" in args:
        dry_run(leads)
        sys.exit(0)

    print("testing freshworks connection...")
    if not test_connection():
        sys.exit(1)
    print()

    sync(leads)
