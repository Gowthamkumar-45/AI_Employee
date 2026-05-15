#!/usr/bin/env python3
"""
AI Employee MCP server.

Exposes the project's skills as MCP tools so a remote Claude Code client
(your friend) can use them without ever seeing the source code.

Each tool spawns an inner Claude session inside this project dir, so the inner
agent inherits CLAUDE.md, skills/, scripts/, .claude/settings.json, and all
secrets from .env. The remote client only sees tool names + docstrings.

Run via scripts/run_mcp_server.sh (which also starts a cloudflared tunnel).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

try:
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
except ImportError:
    from fastmcp.server.auth.providers.bearer import StaticTokenVerifier  # type: ignore

from claude_agent_sdk import ClaudeAgentOptions, query

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

TOKEN = (os.environ.get("AI_EMPLOYEE_MCP_TOKEN") or "").strip()
if not TOKEN:
    print(
        "AI_EMPLOYEE_MCP_TOKEN is not set in .env.\n"
        'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"',
        file=sys.stderr,
    )
    sys.exit(1)

verifier = StaticTokenVerifier(
    tokens={TOKEN: {"client_id": "remote-friend", "scopes": ["use"]}},
    required_scopes=["use"],
)

mcp = FastMCP("ai-employee", auth=verifier)


async def _run_skill(instruction: str) -> str:
    """Run the inner Claude session against this project and return its final text."""
    chunks: list[str] = []
    try:
        async for message in query(
            prompt=instruction,
            options=ClaudeAgentOptions(
                cwd=str(PROJECT_DIR),
                permission_mode="bypassPermissions",
            ),
        ):
            content = getattr(message, "content", None)
            if not content:
                continue
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
    except Exception as exc:
        return f"[ai-employee error] {type(exc).__name__}: {exc}"
    return "\n".join(chunks).strip() or "(no output)"


@mcp.tool
async def scout(query_text: str) -> str:
    """Source and verify new startup leads via Apollo + Lusha. Adds qualified ones to the pipeline.

    Args:
        query_text: Who to find. Example: "10 SaaS founders in Bangalore with 10-50 employees".
    """
    return await _run_skill(
        f"Run the scout-lead skill. Find leads matching: {query_text}. "
        "Add them to data/leads.db with stage=scouted and return a short summary."
    )


@mcp.tool
async def process_lead(name: str, email: str, company: str = "", source: str = "manual") -> str:
    """Take a user-provided lead through the full workflow: enrich, qualify, draft outreach.

    Args:
        name: Lead's full name.
        email: Business email.
        company: Company name. Optional, will be enriched if missing.
        source: Where the lead came from. Default "manual".
    """
    return await _run_skill(
        f"Run the process-lead skill. Lead: {name} <{email}> at "
        f"{company or '(unknown)'} (source: {source})."
    )


@mcp.tool
async def qualify(email: str) -> str:
    """Score an existing pipeline lead and decide the next action.

    Args:
        email: Lead's email (must already be in data/leads.db).
    """
    return await _run_skill(f"Run the qualify-lead skill for {email}.")


@mcp.tool
async def draft_outreach(email: str) -> str:
    """Draft a personalised cold outreach email. Saves to Gmail Drafts. Never sends.

    Args:
        email: Lead's email.
    """
    return await _run_skill(
        f"Run the write-outreach skill for {email}. Save the draft to Gmail Drafts. "
        "Do not send. Return the draft body so the caller can review it."
    )


@mcp.tool
async def resend(email: str) -> str:
    """Send a follow-up to a lead who has not replied.

    Args:
        email: Lead's email.
    """
    return await _run_skill(f"Run the resend-mail skill for {email}.")


@mcp.tool
async def book_call(email: str, when_hint: str = "") -> str:
    """Schedule a discovery call for an interested lead.

    Args:
        email: Lead's email.
        when_hint: Optional time preference. Example: "next Tuesday afternoon".
    """
    return await _run_skill(
        f"Run the book-call skill for {email}. "
        f"Time preference: {when_hint or 'any reasonable slot this week'}."
    )


@mcp.tool
async def same_day_booking(email: str) -> str:
    """When a lead asks to meet TODAY, propose live Calendly slots for the next 12h.

    Args:
        email: Lead's email.
    """
    return await _run_skill(f"Run the same-day-booking skill for {email}.")


@mcp.tool
async def send_thank_you(email: str) -> str:
    """Send a personalised thank-you note after a meeting.

    Args:
        email: Lead's email.
    """
    return await _run_skill(f"Run the send-thank-you skill for {email}.")


@mcp.tool
async def close_notification(email: str, outcome: str, notes: str = "") -> str:
    """Notify admin via Slack when a deal closes.

    Args:
        email: Lead's email.
        outcome: "won" or "lost".
        notes: Optional context, e.g. deal size or reason lost.
    """
    return await _run_skill(
        f"Run the close-notification skill for {email}. "
        f"Outcome: {outcome}. Notes: {notes or '(none)'}."
    )


@mcp.tool
async def track_replies() -> str:
    """Check Gmail and Calendly for new replies and bookings, then update the pipeline."""
    return await _run_skill("Run the track-replies skill now.")


@mcp.tool
def pipeline_status() -> str:
    """Show the current state of the lead pipeline (stages, counts, recent events)."""
    result = subprocess.run(
        ["python3", "scripts/db.py", "list"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
    )
    return (result.stdout + result.stderr).strip() or "(empty pipeline)"


@mcp.tool
def show_lead(email: str) -> str:
    """Show full details for one lead.

    Args:
        email: Lead's email.
    """
    result = subprocess.run(
        ["python3", "scripts/db.py", "show", email],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
    )
    return (result.stdout + result.stderr).strip() or "(not found)"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    mcp.run(transport="http", host=host, port=port)
