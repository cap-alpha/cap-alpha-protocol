#!/bin/bash
# Post a GitHub comment signed with the agent's identity.
#
# Every agent comment on this repo MUST go through this script so that
# each agent's work is clearly attributed and traceable.
#
# Usage:
#   .agent/gh-comment.sh issue 129 "claude-opus-4-go-a1b2" <<'EOF'
#   🤖 intending to work on this at 2026-04-23T14:30:00Z
#   EOF
#
#   echo "CI is green — queued for merge." | .agent/gh-comment.sh pr 151 "claude-sonnet-4-land-c3d4"
#
# The script appends a machine-readable signature line:
#   ---
#   🤖 <agent-id> · <UTC timestamp>
#
# This lets anyone (human or agent) trace which agent posted what.

set -euo pipefail

TYPE="${1:?usage: gh-comment.sh issue|pr <number> <agent-id> (message on stdin)}"
NUMBER="${2:?number required}"
AGENT_ID="${3:?agent-id required}"

# Read message body from stdin
MESSAGE="$(cat)"

if [ -z "$MESSAGE" ]; then
    echo "✗ Empty message body — pipe your comment text to stdin" >&2
    exit 1
fi

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BODY="${MESSAGE}

---
🤖 ${AGENT_ID} · ${TIMESTAMP}"

case "$TYPE" in
    issue) gh issue comment "$NUMBER" --body "$BODY" ;;
    pr)    gh pr comment "$NUMBER" --body "$BODY" ;;
    *)     echo "✗ Unknown type: $TYPE (use 'issue' or 'pr')" >&2; exit 1 ;;
esac
