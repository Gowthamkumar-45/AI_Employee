# Same-Day Booking Skill

When a lead's reply indicates same-day urgency, propose specific Calendly slots
instead of just the generic scheduling link. Time matters when someone wants to
meet today.

## Trigger phrases (URGENT_TODAY classification)

If the reply body contains any of:
- "today" / "tonight" / "this afternoon" / "this evening" / "right now"
- "asap" / "ASAP" / "as soon as possible"
- "today itself" / "before EOD" / "by end of day"
- "now" (in a scheduling context)
- specific same-day times: "in 30 min", "an hour", "a couple hours"

Then run this skill instead of the regular reply flow.

## Step 1: Resolve the host event type

- default event: **30 Minute Meeting** (30 min)
  - URI: `https://api.calendly.com/event_types/a68cf218-9c4b-448e-85f7-90d38486b444`
  - public URL: `https://calendly.com/gowtham-startupculture/30min`

## Step 2: Fetch today's available slots

Call `mcp__claude_ai_Calendly__event_types-list_event_type_available_times`:

```json
{
  "event_type": "https://api.calendly.com/event_types/a68cf218-9c4b-448e-85f7-90d38486b444",
  "start_time": "<now in ISO 8601 UTC>",
  "end_time": "<now + 12 hours in ISO 8601 UTC>"
}
```

This returns available time slots in the host's calendar for the next 12 hours.

## Step 3: Pick 2-3 slots

Take the first 2-3 slots returned. Display each in **IST** for Indian leads
(or the lead's apparent timezone if you can infer it from their phone country
code). Format: "today at HH:MM IST" or "tonight at HH:MM IST".

## Step 4: Draft the reply

Template:

```
to: <lead_email>
subject: Re: <original subject>

hey <first_name>,

happy to chat today. here are the slots i have open:

  - today at 7:00 PM IST
  - today at 7:30 PM IST
  - today at 8:00 PM IST

reply with whichever works and i'll send a calendar invite. or grab any
slot directly:

https://calendly.com/gowtham-startupculture/30min

gowtham
team@startupculture.co.in
```

## Step 5: Show draft, wait for approval, then send

Per the standard rule: never auto-send. Show draft, wait for user to say "send".

## Step 6: After sending, log

```bash
python3 scripts/db.py event <email> note "proposed same-day slots: <slot1>, <slot2>, <slot3>"
python3 scripts/db.py update <email> next_step="awaiting lead's slot pick"
```

## Edge case: no slots available today

If the Calendly API returns zero available times in the next 12 hours, the
draft becomes:

```
hey <first_name>,

today's filling up — i don't have a slot open till tomorrow morning. here's
my calendar — pick whatever works:

https://calendly.com/gowtham-startupculture/30min

happy to make tomorrow morning work if you're free.

gowtham
```

## Where the routine handles this

The remote `sales-pipeline-monitor` routine ALSO classifies replies. When it
sees URGENT_TODAY, it fetches today's slots and includes them in the Slack DM
to you, so you have the slot info already when you decide how to respond.
