#!/bin/bash
# PostToolUse hook - logs structured usage events to .claude/usage_log.jsonl
#
# Claude Code passes hook data via stdin as a JSON object.
# Appends one JSON line per invocation. Never rewrites history.
# Raw command content and file content are never logged.
#
# Exit code 0 always (PostToolUse hooks cannot block execution).

set -euo pipefail

LOG_FILE="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}/.claude/usage_log.jsonl"
input="$(cat)"

# Extract tool name from stdin JSON
tool_name=$(printf "%s" "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_name", d.get("tool", "unknown")))
except Exception:
    print("unknown")
' 2>/dev/null || echo "unknown")

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
session="${CLAUDE_SESSION_ID:-${ANTHROPIC_SESSION_ID:-unknown}}"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"

# Categorize Bash commands without logging raw command text
category=""
if [ "$tool_name" = "Bash" ]; then
    first_token=$(printf "%s" "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    inp = d.get("tool_input", {})
    cmd = inp.get("command", "") if isinstance(inp, dict) else str(inp)
    toks = cmd.strip().split()
    print(toks[0] if toks else "")
except Exception:
    print("")
' 2>/dev/null || echo "")
    case "$first_token" in
        git)           category="git" ;;
        gh)            category="gh" ;;
        make)          category="make" ;;
        python*|pip*)  category="python" ;;
        docker*)       category="docker" ;;
        *)             category="other" ;;
    esac
fi

# For file-editing tools: capture path and operation type, never content
file_path=""
operation=""
if [[ "$tool_name" =~ ^(Edit|Write|MultiEdit|NotebookEdit)$ ]]; then
    file_path=$(printf "%s" "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    inp = d.get("tool_input", {})
    print(inp.get("file_path", inp.get("path", "")) if isinstance(inp, dict) else "")
except Exception:
    pass
' 2>/dev/null || echo "")
    operation="$tool_name"
fi

# Infer work phase from tool name / command category
case "$tool_name" in
    Read|Glob|Grep)       phase="planning" ;;
    Edit|Write|MultiEdit) phase="coding" ;;
    Bash)
        case "$category" in
            gh)   phase="landing" ;;
            *)    phase="executing" ;;
        esac ;;
    *)                    phase="other" ;;
esac

# Write JSON record via Python for correct escaping
python3 - "$LOG_FILE" "$ts" "$tool_name" "$phase" "$branch" "$session" "$category" "$file_path" "$operation" <<'PYEOF'
import json, sys
log_path, ts, tool, phase, branch, session, category, file_path, operation = sys.argv[1:]
record = {
    "ts": ts,
    "event": "tool_call",
    "tool": tool,
    "phase": phase,
    "branch": branch,
    "session": session,
}
if category:
    record["category"] = category
if file_path:
    record["file_path"] = file_path
    record["operation"] = operation
try:
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
except Exception:
    pass
PYEOF

exit 0
