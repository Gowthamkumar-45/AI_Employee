#!/usr/bin/env python3
"""Lead database — SQLite-backed source of truth for all leads.

Replaces memory/pipeline.md as the canonical store. pipeline.md is now
generated on demand via `python3 scripts/db.py export`.

CLI:
    db.py init                                    # create DB + schema (idempotent)
    db.py list                                    # all leads
    db.py list --stage outreach                   # filter by stage
    db.py show <email>                            # one lead with events
    db.py add --name X --email Y [--stage ...]    # create lead
    db.py update <email> stage=replied notes=...  # update fields
    db.py event <email> <type> [detail]           # log a lead event
    db.py export [--out memory/pipeline.md]       # regen markdown view

Library use:
    import db
    db.add_lead(name="...", email="...", ...)
    leads = db.list_leads(stage="outreach")
    db.update_lead("rachel@x.com", stage="replied")
    db.add_event("rachel@x.com", "reply", "interested")
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "leads.db"

LEAD_FIELDS = [
    "name", "company", "role", "email", "phone", "linkedin",
    "other_social", "source", "campaign", "verification_status",
    "qualification_status", "stage", "next_step", "notes",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    company TEXT,
    role TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    linkedin TEXT,
    other_social TEXT,
    source TEXT,
    campaign TEXT,
    verification_status TEXT,
    qualification_status TEXT,
    stage TEXT NOT NULL DEFAULT 'scouted',
    next_step TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_events_lead_id ON events(lead_id);

CREATE TRIGGER IF NOT EXISTS trg_leads_updated_at
AFTER UPDATE ON leads
FOR EACH ROW
BEGIN
    UPDATE leads SET updated_at = datetime('now') WHERE id = NEW.id;
END;
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---- CRUD ------------------------------------------------------------------

def add_lead(**kwargs) -> int | None:
    """Insert a lead. Returns new id, or None if email already exists."""
    init_db()
    fields = {k: v for k, v in kwargs.items() if k in LEAD_FIELDS and v not in (None, "")}
    if "name" not in fields:
        raise ValueError("name is required")
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    with get_conn() as conn:
        try:
            cur = conn.execute(
                f"INSERT INTO leads ({cols}) VALUES ({placeholders})",
                tuple(fields.values()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def upsert_lead(**kwargs) -> int:
    """Insert or update by email. Returns lead id."""
    email = kwargs.get("email")
    if email:
        existing = get_lead_by_email(email)
        if existing:
            update_lead(email, **{k: v for k, v in kwargs.items() if k != "email"})
            return existing["id"]
    return add_lead(**kwargs)


def get_lead_by_email(email: str) -> dict | None:
    if not email:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def list_leads(stage: str | None = None, source: str | None = None,
               campaign: str | None = None) -> list[dict]:
    query = "SELECT * FROM leads WHERE 1=1"
    params: list = []
    if stage:
        query += " AND stage = ?"
        params.append(stage)
    if source:
        query += " AND source LIKE ?"
        params.append(f"%{source}%")
    if campaign:
        query += " AND campaign = ?"
        params.append(campaign)
    query += " ORDER BY id"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def update_lead(email: str, **kwargs) -> bool:
    fields = {k: v for k, v in kwargs.items() if k in LEAD_FIELDS}
    if not fields:
        return False
    sets = ", ".join(f"{k} = ?" for k in fields.keys())
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE leads SET {sets} WHERE email = ?",
            tuple(fields.values()) + (email,),
        )
        return cur.rowcount > 0


def add_event(email: str, event_type: str, detail: str | None = None) -> int | None:
    with get_conn() as conn:
        lead = conn.execute("SELECT id FROM leads WHERE email = ?", (email,)).fetchone()
        if not lead:
            return None
        cur = conn.execute(
            "INSERT INTO events (lead_id, event_type, detail) VALUES (?, ?, ?)",
            (lead["id"], event_type, detail),
        )
        return cur.lastrowid


def get_events(email: str) -> list[dict]:
    with get_conn() as conn:
        lead = conn.execute("SELECT id FROM leads WHERE email = ?", (email,)).fetchone()
        if not lead:
            return []
        rows = conn.execute(
            "SELECT * FROM events WHERE lead_id = ? ORDER BY created_at DESC",
            (lead["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


def sync_to_freshworks(email: str) -> str:
    """Push a lead's current DB state to Freshworks CRM.
    Returns a status string. Failures are non-fatal."""
    if not email:
        return "skipped (no email)"
    try:
        # lazy import to avoid circular dep and missing-deps crashes
        from freshworks_sync import create_or_update, load_leads  # type: ignore
    except Exception as exc:
        return f"freshworks module unavailable ({exc})"

    matched = [l for l in load_leads() if l["email"] == email]
    if not matched:
        return "not in DB"
    try:
        result, detail = create_or_update(matched[0])
        return f"{result} ({detail})" if result == "failed" else result
    except Exception as exc:
        return f"error: {exc}"


def stats() -> dict:
    """Return per-stage counts + total."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT stage, COUNT(*) AS c FROM leads GROUP BY stage ORDER BY c DESC"
        ).fetchall()
        return {"by_stage": {r["stage"]: r["c"] for r in rows},
                "total": sum(r["c"] for r in rows)}


# ---- Markdown export -------------------------------------------------------

def export_markdown(out_path: str | Path) -> Path:
    leads = list_leads()
    s = stats()

    lines = [
        "# Pipeline (auto-generated)",
        "",
        f"> Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from `data/leads.db`.",
        "> Do not edit by hand — use `python3 scripts/db.py` instead.",
        "",
        f"**Total leads:** {s['total']}",
        "",
        "## By stage",
        "",
        "| Stage | Count |",
        "|---|---|",
    ]
    for stage, c in s["by_stage"].items():
        lines.append(f"| {stage} | {c} |")
    lines += ["", "## Leads (one-line view)", "",
              "| # | Name | Company | Email | Stage | Next step |",
              "|---|---|---|---|---|---|"]
    for i, l in enumerate(leads, 1):
        lines.append(
            f"| {i} | {l['name'] or ''} | {l.get('company') or ''} | "
            f"{l.get('email') or ''} | {l['stage']} | {l.get('next_step') or ''} |"
        )
    lines.append("")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def export_routine_leads(out_path: str | Path) -> Path:
    """Write outreach-stage leads as JSON for the remote routine to fetch
    via raw.githubusercontent.com. Includes only leads with a real email."""
    import json
    rows = list_leads(stage="outreach")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "leads": [
            {
                "name": r["name"],
                "email": r["email"],
                "company": r.get("company") or "",
            }
            for r in rows if r.get("email")
        ],
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


# ---- CLI -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Lead database CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create DB + schema (idempotent)")

    p_list = sub.add_parser("list", help="List leads")
    p_list.add_argument("--stage")
    p_list.add_argument("--source")
    p_list.add_argument("--campaign")

    p_show = sub.add_parser("show", help="Show one lead + events")
    p_show.add_argument("email")

    p_add = sub.add_parser("add", help="Add a lead (auto-syncs to Freshworks if email present)")
    for f in LEAD_FIELDS:
        p_add.add_argument(f"--{f.replace('_', '-')}")
    p_add.add_argument("--no-sync", action="store_true",
                       help="skip Freshworks sync (DB only)")

    p_update = sub.add_parser("update", help="Update lead by email (auto-syncs to Freshworks)")
    p_update.add_argument("email")
    p_update.add_argument("kv", nargs="+", help="key=value pairs")
    p_update.add_argument("--no-sync", action="store_true",
                          help="skip Freshworks sync (DB only)")

    p_event = sub.add_parser("event", help="Log an event for a lead")
    p_event.add_argument("email")
    p_event.add_argument("event_type",
                         help="one of: email_sent, reply, booking, meeting, note, stage_change")
    p_event.add_argument("detail", nargs="?")

    p_export = sub.add_parser("export", help="Write markdown view from DB")
    p_export.add_argument("--out",
                          default=str(Path(__file__).parent.parent / "memory" / "pipeline.md"))

    p_export_routine = sub.add_parser("export-routine",
                                       help="Write JSON of outreach-stage leads for the remote routine to fetch")
    p_export_routine.add_argument("--out",
                                   default=str(Path(__file__).parent.parent / "data" / "routine_leads.json"))

    sub.add_parser("stats", help="Print stage summary")

    args = parser.parse_args()

    if args.cmd == "init":
        init_db()
        print(f"DB ready at {DB_PATH}")

    elif args.cmd == "list":
        leads = list_leads(stage=args.stage, source=args.source, campaign=args.campaign)
        print(f"{'#':<4}{'NAME':<28}{'COMPANY':<28}{'EMAIL':<35}{'STAGE':<12}")
        print("-" * 107)
        for i, l in enumerate(leads, 1):
            print(f"{i:<4}{(l['name'] or '')[:27]:<28}"
                  f"{(l.get('company') or '')[:27]:<28}"
                  f"{(l.get('email') or '')[:34]:<35}"
                  f"{(l.get('stage') or '')[:11]:<12}")
        print(f"\n{len(leads)} leads")

    elif args.cmd == "show":
        lead = get_lead_by_email(args.email)
        if not lead:
            print(f"no lead with email {args.email}")
            sys.exit(1)
        for k, v in lead.items():
            if v not in (None, ""):
                print(f"  {k}: {v}")
        events = get_events(args.email)
        if events:
            print("\nevents:")
            for e in events:
                print(f"  [{e['created_at']}] {e['event_type']}: {(e['detail'] or '')[:80]}")

    elif args.cmd == "add":
        kwargs = {f: getattr(args, f, None) for f in LEAD_FIELDS}
        kwargs = {k: v for k, v in kwargs.items() if v}
        if "name" not in kwargs:
            print("--name is required")
            sys.exit(1)
        lead_id = add_lead(**kwargs)
        if lead_id:
            print(f"db: created lead id={lead_id}")
            if not args.no_sync and kwargs.get("email"):
                fw_status = sync_to_freshworks(kwargs["email"])
                print(f"freshworks: {fw_status}")
        else:
            print(f"db: email already exists: {kwargs.get('email')}")

    elif args.cmd == "update":
        kwargs = {}
        for kv in args.kv:
            if "=" not in kv:
                print(f"invalid key=value: {kv}")
                sys.exit(1)
            k, v = kv.split("=", 1)
            kwargs[k] = v
        if update_lead(args.email, **kwargs):
            print(f"db: updated {args.email} → {kwargs}")
            if "stage" in kwargs:
                add_event(args.email, "stage_change", f"→ {kwargs['stage']}")
            if not args.no_sync:
                fw_status = sync_to_freshworks(args.email)
                print(f"freshworks: {fw_status}")
        else:
            print(f"no lead found or no fields updated: {args.email}")

    elif args.cmd == "event":
        eid = add_event(args.email, args.event_type, args.detail)
        if eid:
            print(f"logged event id={eid}: {args.event_type}")
        else:
            print(f"no lead found: {args.email}")

    elif args.cmd == "export":
        out = export_markdown(args.out)
        print(f"exported to {out}")

    elif args.cmd == "export-routine":
        out = export_routine_leads(args.out)
        rows = list_leads(stage="outreach")
        n = len([r for r in rows if r.get("email")])
        print(f"exported {n} outreach-stage leads with email to {out}")
        print("next: git add data/routine_leads.json && git commit -m 'update routine lead list' && git push")

    elif args.cmd == "stats":
        s = stats()
        print(f"total: {s['total']}")
        for stage, c in s["by_stage"].items():
            print(f"  {stage}: {c}")


if __name__ == "__main__":
    main()
