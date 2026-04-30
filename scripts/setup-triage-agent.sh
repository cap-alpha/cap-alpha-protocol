#!/usr/bin/env bash
# setup-triage-agent.sh — idempotent setup for com.capalpha.triage-agent launchd job.
# Safe to run multiple times.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# git --git-common-dir points at the main .git regardless of worktree; parent is the main checkout
_GIT_COMMON="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null | xargs -I{} realpath {} 2>/dev/null || true)"
MAIN_ROOT="$(cd "${_GIT_COMMON}/.." 2>/dev/null && pwd || echo "$REPO_ROOT")"
# .env.personas is always in the main checkout, not the worktree
PERSONAS="${MAIN_ROOT}/.env.personas"
PLIST_TEMPLATE="${REPO_ROOT}/scripts/launchagents/com.capalpha.triage-agent.plist"
PLIST_DEST="${HOME}/Library/LaunchAgents/com.capalpha.triage-agent.plist"
CLAUDE_BIN="/opt/homebrew/bin/claude"
LOG_PATH="${HOME}/Library/Logs/com.capalpha.triage-agent.log"
LOG_LABEL="com.capalpha.triage-agent"

err() { echo "ERROR: $*" >&2; exit 1; }
ok()  { echo "  OK: $*"; }

echo "=== Setting up Autonomous Triage Agent ==="

# 1. Validate claude exists
[[ -x "$CLAUDE_BIN" ]] || err "claude not found at $CLAUDE_BIN. Install via: brew install anthropic/tap/claude"
ok "claude CLI found at $CLAUDE_BIN ($(\"$CLAUDE_BIN\" --version 2>/dev/null | head -1 || echo 'version unknown'))"

# 2. Validate .env.personas
[[ -f "$PERSONAS" ]] || err ".env.personas not found at $PERSONAS. Create it with GH_APP_ID, GH_INSTALLATION_ID, and SLACK_WEBHOOK_URL."
# Accept either GitHub App identity (GH_APP_ID + GH_INSTALLATION_ID) or legacy PAT (LARS_TOKEN)
if ! grep -q "^GH_APP_ID=" "$PERSONAS" && ! grep -q "^LARS_TOKEN=" "$PERSONAS"; then
    err ".env.personas missing GitHub identity — need GH_APP_ID (App auth) or LARS_TOKEN (PAT auth)"
fi
if grep -q "^GH_APP_ID=" "$PERSONAS" && ! grep -q "^GH_INSTALLATION_ID=" "$PERSONAS"; then
    err ".env.personas has GH_APP_ID but is missing GH_INSTALLATION_ID (required for App auth)"
fi
grep -q "^SLACK_WEBHOOK_URL=" "$PERSONAS" || { echo "  WARN: SLACK_WEBHOOK_URL not set — Slack alerts disabled"; }
ok ".env.personas validated"

# 3. Validate plist template exists
[[ -f "$PLIST_TEMPLATE" ]] || err "plist template not found at $PLIST_TEMPLATE"

# 4. Substitute paths and write plist
# REPO_ROOT_PLACEHOLDER → main checkout (not worktree) so launchd uses the stable path
mkdir -p "${HOME}/Library/LaunchAgents"
sed \
    -e "s|REPO_ROOT_PLACEHOLDER|${MAIN_ROOT}|g" \
    -e "s|HOME_PLACEHOLDER|${HOME}|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"
ok "plist written to $PLIST_DEST"

# 5. Reload launchd job (idempotent: unload first, ignore error if not loaded)
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
ok "launchd job loaded"

# 6. Verify job is registered
if launchctl list | grep -q "$LOG_LABEL"; then
    ok "launchctl confirmed: $LOG_LABEL is registered"
else
    err "launchctl did not register $LOG_LABEL — check plist syntax"
fi

# 7. Dry-run to verify the script works end-to-end
echo ""
echo "--- Running --dry-run ---"
bash "${REPO_ROOT}/scripts/triage-agent.sh" --dry-run
echo "--- End dry-run ---"
echo ""

# 8. Print next-run time and log path
echo "=== Setup complete ==="
echo "  Schedule           : every 10 minutes"
echo "  Log file           : $LOG_PATH"
echo "  Disable with       : make uninstall-triage-agent"
echo ""
echo "Tip: tail -f $LOG_PATH"
