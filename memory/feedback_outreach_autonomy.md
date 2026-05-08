---
name: outreach drafting autonomy
description: User wants the agent to scout, qualify, and draft outreach emails fully automatically; only the SEND step requires human approval.
type: feedback
---

For this AI sales employee project, the agent should run scout → enrich → qualify → DRAFT autonomously without asking permission between steps. Drafts go to Gmail Drafts folder. The agent then stops and notifies the user via Slack (Stop hook handles this).

The user verifies the drafts in Gmail and either:
- replies "send them" / "send it" → agent sends via Gmail
- sends the drafts themselves from the Gmail UI
- requests edits → agent redrafts and stops again

**Why:** User stated this explicitly — they don't want to be asked "should I draft?" at every step. Asking for permission to draft slows them down. They only want a checkpoint before sending, since sent emails are irreversible.

**How to apply:** When the user provides leads or asks to scout/process leads, run the entire pipeline up to and including draft creation without further prompts. Stop ONLY at the send boundary. Never call Gmail send (or any send-equivalent) without an explicit user "send" command.
