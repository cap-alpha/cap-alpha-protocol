#!/usr/bin/env bash
# uninstall-triage-agent.sh — remove launchd job and optionally the plist.

set -euo pipefail

PLIST_DEST="${HOME}/Library/LaunchAgents/com.capalpha.triage-agent.plist"
LOG_LABEL="com.capalpha.triage-agent"

echo "=== Uninstalling Autonomous Triage Agent ==="

launchctl unload "$PLIST_DEST" 2>/dev/null && echo "  Unloaded: $LOG_LABEL" || echo "  Not loaded (already unloaded or never installed)"

if [[ -f "$PLIST_DEST" ]]; then
    rm "$PLIST_DEST"
    echo "  Removed plist: $PLIST_DEST"
fi

echo "=== Done. Re-install with: make setup-triage-agent ==="
