# Connect to AI Employee from your Claude Code

You don't need to install anything except Claude Code. The AI Employee runs on
Gowtham's machine. Your Claude Code just talks to it over the network.

## What Gowtham sends you (out-of-band, e.g. Signal)

1. A tunnel URL like `https://<random>.trycloudflare.com`
2. A bearer token (long random string)

Both change if his server restarts, so check before each session.

## One-time-per-URL setup

In a terminal:

```bash
claude mcp add ai-employee \
  --transport http \
  --header "Authorization=Bearer <TOKEN_FROM_GOWTHAM>" \
  <TUNNEL_URL_FROM_GOWTHAM>
```

If your `claude` CLI uses a different argument order, the equivalent JSON entry
in `~/.claude.json` (under `"mcpServers"`) is:

```json
"ai-employee": {
  "transport": "http",
  "url": "https://<random>.trycloudflare.com",
  "headers": { "Authorization": "Bearer <TOKEN>" }
}
```

Then in Claude Code run `/mcp` and confirm `ai-employee` is listed as
connected.

## Using it

Just type what you want in plain English. Claude will pick the right tool:

- "scout 10 SaaS founders in Bangalore" → `ai-employee.scout`
- "qualify alice@acme.com" → `ai-employee.qualify`
- "draft outreach for alice@acme.com" → `ai-employee.draft_outreach`
- "what's in the pipeline?" → `ai-employee.pipeline_status`

Available tools:

| Tool | What it does |
|---|---|
| `scout` | Find new leads via Apollo + Lusha |
| `process_lead` | Take a user-provided lead through the full workflow |
| `qualify` | Score a lead |
| `draft_outreach` | Draft cold email to Gmail Drafts. Never sends. |
| `resend` | Send a follow-up |
| `book_call` | Schedule a discovery call |
| `same_day_booking` | Propose Calendly slots for today |
| `send_thank_you` | Post-meeting thank-you note |
| `close_notification` | Slack admin when a deal closes |
| `track_replies` | Check Gmail + Calendly, update pipeline |
| `pipeline_status` | List all leads |
| `show_lead` | Full details for one lead |

## Things to know

- **No data stays on your machine.** Lead DB, drafts, secrets all live on
  Gowtham's laptop.
- **If his laptop is asleep or offline**, every tool call returns a connection
  error. There is no queue.
- **Emails get sent from Gowtham's Gmail**, calls go on his Calendly, Slack
  pings go to his admin channel. If that's not what you want, ask him to set
  up a per-user variant.
- **Token rotation revokes access.** If he generates a new token, you'll get
  401 errors until he sends you the new one.
