# Track Replies Skill

When the user asks to "check for replies", "monitor outreach", "what's new", or
"track lead status", run the full event-detection loop:

## Step 1: Detect email events

For every lead in `memory/pipeline.md` whose stage is `outreach` or
`follow-up`, search Gmail for their email thread:

- use `mcp__claude_ai_Gmail__search_threads` with `from:<lead_email>`
- check the most recent thread for replies AFTER our last outreach
- detect signal type:
  - **interested**: phrases like "yes", "sure", "let's talk", "sounds good",
    "happy to chat", "send me a calendar link", "schedule a call"
  - **not interested**: "no thanks", "not a fit", "not now", "unsubscribe"
  - **needs more info**: "tell me more", "what does it cost", "how does it work"
  - **out of office / auto-reply**: ignore
  - **bounce / undelivered**: mark contact email as invalid

## Step 2: Detect calendar bookings

- use `mcp__claude_ai_Calendly__meetings-list_events` to pull recent events
- for each event, get the invitee email via `meetings-list_event_invitees`
- match invitee email to a pipeline.md lead
- if matched and the meeting is in the future → stage = `booked`
- if matched and the meeting is in the past → stage = `met`

## Step 3: Update pipeline.md

For each detected event, edit the lead block:
- update `Current stage` to the new stage
- update `Next step` to reflect the action needed:
  - `interested` → `send proposal / book call`
  - `not interested` → `mark lost`
  - `booked` → `prep for call on <date>`
  - `met` → `send thank-you note + action items`
- append the event to `Notes` with a timestamp:
  `[2026-05-08] reply received: "<short snippet>"`

## Step 4: Sync to Freshworks

After updating pipeline.md, run the sync script for every changed lead:

```bash
python3 scripts/freshworks_sync.py --update <lead_email> <new_stage>
```

Or do a full sync to push everything at once:

```bash
python3 scripts/freshworks_sync.py
```

## Step 5: Trigger downstream skills

Based on the new stage:
- `interested` → run [`book-call.md`](book-call.md) to send a Calendly link
- `booked` → schedule a Fireflies bot for the meeting (if integrated)
- `met` → run [`send-thank-you.md`](send-thank-you.md)
- `won` / `lost` → run [`close-notification.md`](close-notification.md)

## Step 6: Report to user

Print a summary of what changed:

```
3 events detected since last check:
  → Rachel Bacheler replied (interested) — book call
  → Jeremy Abesera booked a call for 2026-05-12 14:00
  → Charles Brandon replied (not interested) — marked lost

pipeline.md updated. Freshworks synced.
```
