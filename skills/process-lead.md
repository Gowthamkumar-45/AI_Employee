# Process Lead

This skill is for handling leads you provide directly to the AI employee.

When you give a lead to the AI employee, it should run the full workflow for that lead.

## Step 1: Review the provided lead
- read the lead details the user provided
- confirm the name, company, role, email, phone, LinkedIn, and any social profiles
- check if any required information is missing

## Step 2: Verify and enrich
- verify the lead is real using Lusha, public profiles, or company data
- enrich incomplete contact details where possible
- do not proceed if the lead cannot be confirmed as real

## Step 3: Qualify the lead
- confirm company fit, role fit, and decision power
- identify the lead's product needs or pain points
- mark the lead ready for outreach if it passes qualification

## Step 4: Execute outreach
- write personalised first-touch outreach based on the lead details and profile signals
- send the email through Gmail
- schedule follow-ups or resend if there is no reply

## Step 5: Book and follow up
- if the lead is interested, book a discovery call via Calendly
- capture call notes with Fireflies during the meeting
- send a personalised thank-you note after the call

## Step 6: Close and notify
- if the lead closes won or lost, notify admin via Slack
- update memory/pipeline.md with the final outcome

## Rules
- if the lead is provided by the user, do not require a separate scouting prompt
- use the same process as scouting leads, but skip the source discovery step
- keep memory files updated at every stage
