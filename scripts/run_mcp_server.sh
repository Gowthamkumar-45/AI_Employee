#!/usr/bin/env bash
# Start the AI Employee MCP server and expose it via a cloudflared quick tunnel.
# Friend connects from their Claude Code using the printed URL + the bearer token from .env.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f .env ]; then
  echo "Missing .env at $PROJECT_DIR/.env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [ -z "${AI_EMPLOYEE_MCP_TOKEN:-}" ]; then
  echo "AI_EMPLOYEE_MCP_TOKEN is empty in .env." >&2
  echo 'Generate one:  python3 -c "import secrets; print(secrets.token_urlsafe(32))"' >&2
  exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed. Install with:  brew install cloudflared" >&2
  exit 1
fi

python3 scripts/mcp_server.py &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

sleep 1
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "MCP server failed to start. Check the output above." >&2
  exit 1
fi

echo
echo "==============================================================="
echo " AI Employee MCP server running on http://127.0.0.1:8765"
echo " Token (share out-of-band): $AI_EMPLOYEE_MCP_TOKEN"
echo "==============================================================="
echo " Starting cloudflared tunnel. The public URL appears below."
echo " Send your friend BOTH that URL and the token above."
echo "==============================================================="
echo

exec cloudflared tunnel --url http://localhost:8765
