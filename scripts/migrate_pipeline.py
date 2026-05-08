#!/usr/bin/env python3
"""One-time migration: parse memory/pipeline.md → insert into data/leads.db.

Run once after creating the DB schema. Subsequent inserts/updates should go
through scripts/db.py directly.

Usage:
    python3 scripts/migrate_pipeline.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402


def field(block, label):
    pattern = rf"\*\*{re.escape(label)}:\*\*\s*(.+)"
    m = re.search(pattern, block)
    return m.group(1).strip() if m else ""


def extract_email(raw):
    m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", raw)
    return m.group(0) if m else ""


def extract_phone(raw):
    if "..." in raw or "to be" in raw.lower() or "available" in raw.lower():
        return ""
    m = re.search(r"[\+\d][\d\s\-\(\)]{6,}", raw)
    return m.group(0).strip() if m else ""


def extract_linkedin(raw):
    m = re.search(r"https?://[^\s)]+linkedin[^\s)]+", raw)
    return m.group(0) if m else ""


def parse_stage(raw):
    s = raw.lower()
    for known in ["lost", "won", "met", "booked", "follow-up", "qualified",
                  "outreach", "scouted"]:
        if known in s:
            return known
    return "scouted"


def infer_campaign(source):
    s = (source or "").lower()
    if "google ads" in s:
        return "naturals-accelerator"
    if "apollo" in s or "linkedin" in s or "lusha" in s:
        return "startupculture-cold-outreach"
    return None


def main():
    pipeline_path = Path(__file__).parent.parent / "memory" / "pipeline.md"
    if not pipeline_path.exists():
        print(f"not found: {pipeline_path}")
        sys.exit(1)

    db.init_db()

    text = pipeline_path.read_text(encoding="utf-8")
    blocks = re.split(r"#{3}\s+Lead\s+\d+", text)

    created = duplicate = skipped = 0
    for block in blocks[1:]:
        name = field(block, "Lead name")
        if "***" in name:
            name = re.sub(r"\*+", "", name).strip()
        if not name:
            skipped += 1
            continue

        source = field(block, "Source") or None
        lead = {
            "name": name,
            "company": field(block, "Company") or None,
            "role": field(block, "Role") or None,
            "email": extract_email(field(block, "Contact email")) or None,
            "phone": extract_phone(field(block, "Phone number")) or None,
            "linkedin": extract_linkedin(field(block, "LinkedIn profile")) or None,
            "source": source,
            "campaign": infer_campaign(source),
            "verification_status": field(block, "Verification status") or None,
            "qualification_status": field(block, "Qualification status") or None,
            "stage": parse_stage(field(block, "Current stage")),
            "next_step": field(block, "Next step") or None,
            "notes": field(block, "Notes") or None,
        }

        lead_id = db.add_lead(**lead)
        if lead_id:
            created += 1
        else:
            duplicate += 1

    print(f"migration done — created: {created}  duplicate: {duplicate}  skipped: {skipped}")
    print(f"db: {db.DB_PATH}")
    s = db.stats()
    print(f"\ntotal in DB: {s['total']}")
    for stage, c in s["by_stage"].items():
        print(f"  {stage}: {c}")


if __name__ == "__main__":
    main()
