#!/usr/bin/env bash
# Slack notification hook — sends the last assistant message to Slack
# whenever Claude finishes a turn. Reads hook input JSON from stdin.
#
# Requires SLACK_WEBHOOK_URL in .env or shell environment.
# Webhook setup: https://api.slack.com/apps → Incoming Webhooks

set -u

# Source .env if present (silently)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

# Silently exit if webhook not configured
if [ -z "${SLACK_WEBHOOK_URL:-}" ]; then
  exit 0
fi

# jq is required for parsing
command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""')

# Fallback: construct transcript path from cwd
if [ -z "$TRANSCRIPT_PATH" ] && [ -n "$SESSION_ID" ]; then
  CWD=$(pwd)
  SANITIZED=$(echo "$CWD" | sed 's|/|-|g')
  TRANSCRIPT_PATH="$HOME/.claude/projects/$SANITIZED/$SESSION_ID.jsonl"
fi

# Extract last assistant text from transcript
SUMMARY="task complete"
if [ -f "$TRANSCRIPT_PATH" ]; then
  EXTRACTED=$(tail -300 "$TRANSCRIPT_PATH" 2>/dev/null \
    | jq -r 'select(.message.role == "assistant") | .message.content[]? | select(.type == "text") | .text' 2>/dev/null \
    | tail -c 1500 \
    | sed 's/[[:space:]]\{2,\}/ /g')
  if [ -n "$EXTRACTED" ]; then
    SUMMARY="$EXTRACTED"
  fi
fi

PROJECT=$(basename "$(pwd)")
MESSAGE="claude finished — $PROJECT

$SUMMARY"

# Post to Slack — fail silently to avoid blocking Claude
PAYLOAD=$(jq -nc --arg text "$MESSAGE" '{text: $text}')
curl -s --max-time 5 -X POST -H 'Content-Type: application/json' \
  -d "$PAYLOAD" "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true

exit 0
