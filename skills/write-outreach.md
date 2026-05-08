# Write Outreach Skill

When a lead is qualified and ready for first-touch contact, do this:

## Step 1: Review lead context

- read the lead's pipeline.md entry, qualification notes, and company details
- identify a real challenge or product need they likely have
- check LinkedIn / social profiles for recent activity if available
- pick one specific, recent detail to reference (avoids generic outreach)

## Step 2: Write the first-touch email

- tone: lowercase, casual, direct, no corporate speak, no emojis,
  no dashes as thought separators
- structure:
  1. one specific reason the lead matters (reference their company / signal)
  2. who we are at startupculture and what we do
  3. how that maps to their likely pain
  4. simple CTA — Calendly link + reply option

## Step 3: ALWAYS include the Calendly link

Every outreach email must include the public scheduling URL so interested
leads can self-book without needing to reply first:

```
https://calendly.com/mm-kumarrr123/startup-discovery-call
```

This is a 30-min "Startup Discovery Call" event. Use this same link for all
cold outreach. (For replies after a lead has expressed interest, generate
a single-use link via book-call.md instead.)

## Step 4: Email template

```
to: <lead_email>
subject: <short, lowercase, specific to the lead>

hey <first_name>,

<one specific opening line about their company / a recent signal>

i'm at startupculture — we build software for product-first brands.
<one line connecting our work to their likely pain>.

if any of that resonates, grab a 30 min slot:
https://calendly.com/mm-kumarrr123/startup-discovery-call

or just reply if email's easier.

gowtham
team@startupculture.co.in
```

## Step 5: Show draft to user before sending

- print the full draft (to / subject / body) in chat
- ask: "send it?" or "create as draft?"
- DO NOT send until the user confirms

## Step 6: Create the draft via Gmail

- once approved, use `mcp__claude_ai_Gmail__create_draft`
- this saves to the user's Gmail Drafts folder
- the user clicks Send in Gmail UI to actually deliver

## Step 7: Update memory/pipeline.md

- set `Current stage:` to `outreach`
- set `Next step:` to `wait for reply or booking — routine monitors automatically`
- append `Notes:` with `[YYYY-MM-DD] outreach draft created`

## Step 8: Sync to Freshworks

```bash
python3 scripts/freshworks_sync.py --update <lead_email> outreach
```
