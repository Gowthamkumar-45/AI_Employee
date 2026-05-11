# Book Call Skill

When a lead replies INTERESTED, the user instructs you to "send the calendly link"
or "book a call with [lead]". Follow this flow exactly. Do not auto-send — always
draft and show the user before sending.

## Step 1: Generate a Calendly scheduling link

- default event type: **30 Minute Meeting** (30 min)
  - URI: `https://api.calendly.com/event_types/a68cf218-9c4b-448e-85f7-90d38486b444`
  - public URL: `https://calendly.com/gowtham-startupculture/30min`
- if the user names a different event type, call `event_types-list_event_types`
  to find it
- create a single-use link via
  `mcp__claude_ai_Calendly__scheduling_links-create_single_use_scheduling_link`:
  ```json
  {
    "owner": "<event_type_uri>",
    "owner_type": "EventType",
    "max_event_count": 1
  }
  ```
- store the returned `booking_url`

## Step 2: Draft the reply email

- pull the original outreach thread from Gmail (search by lead email)
- write a short, casual reply that references their reply
- embed the calendly link clearly
- tone: lowercase, direct, no corporate speak, no emojis, no dashes as separators
- example template:

  ```
  to: <lead_email>
  subject: re: <original subject>

  hey <first_name>,

  awesome, glad you're up for a chat. here's a link to grab a 30 min slot
  that works for you:

  <calendly_booking_url>

  pick whatever's easiest. talk soon.

  gowtham
  team@startupculture.co.in
  ```

## Step 3: Show the draft to the user

- print the full draft (to, subject, body) in chat
- ask: "send it?"
- DO NOT send via Gmail until the user explicitly confirms

## Step 4: Send via Gmail

- once approved, use `mcp__claude_ai_Gmail__create_draft` then send
- if the user rejects or wants edits, redraft and re-show

## Step 5: Update memory/pipeline.md

- find the lead's block in `memory/pipeline.md`
- update fields:
  - **Current stage:** `link-sent` (waiting on booking)
  - **Next step:** wait for booking — routine will detect when scheduled
  - **Notes:** append `[YYYY-MM-DD] sent calendly link: <booking_url>`

## Step 6: Update Freshworks

```bash
python3 scripts/freshworks_sync.py --update <lead_email> outreach
```

(stage stays "outreach" until they actually book — then routine catches it)

## Step 7: When the lead books (handled automatically)

The remote routine catches the booking on its next run. It will:
- detect the Calendly event via `meetings-list_events`
- match invitee email to the lead
- Slack DM the user: "lead booked a call for <date>"
- you don't need to do anything for this part — it's automatic
