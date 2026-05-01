#!/usr/bin/env bash
# dispatch-claude.sh — thin wrapper around `claude -p` that logs token spend
# Usage: dispatch-claude.sh --model <model> --prompt-file <file> --worktree <path> [--env KEY=VAL ...]
# Outputs Claude's response to stdout; appends usage delta to .claude/usage_log.jsonl
#
# IMPORTANT: claude is invoked with CWD set to the worktree so that git operations
# (commit, push, branch) target the correct worktree branch, not the main checkout.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USAGE_LOG="${REPO_ROOT}/.claude/usage_log.jsonl"
CLAUDE_BIN="${CLAUDE_BIN:-/opt/homebrew/bin/claude}"
LOG_LABEL=""
MODEL=""
PROMPT_FILE=""
WORKTREE=""
ENV_VARS=()
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)      MODEL="$2";       shift 2 ;;
        --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
        --worktree)   WORKTREE="$2";    shift 2 ;;
        --label)      LOG_LABEL="$2";   shift 2 ;;
        --env)        ENV_VARS+=("$2"); shift 2 ;;
        *)            EXTRA_ARGS+=("$1"); shift ;;
    esac
done

[[ -z "$MODEL" ]]       && { echo "ERROR: --model required" >&2; exit 1; }
[[ -z "$PROMPT_FILE" ]] && { echo "ERROR: --prompt-file required" >&2; exit 1; }
[[ -z "$WORKTREE" ]]    && { echo "ERROR: --worktree required" >&2; exit 1; }
[[ ! -f "$PROMPT_FILE" ]] && { echo "ERROR: prompt file not found: $PROMPT_FILE" >&2; exit 1; }
[[ ! -d "$WORKTREE" ]]    && { echo "ERROR: worktree not found: $WORKTREE" >&2; exit 1; }
[[ ! -x "$CLAUDE_BIN" ]]  && { echo "ERROR: claude not found at $CLAUDE_BIN" >&2; exit 1; }

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
START_TS="$(ts)"

# Build env command: `env KEY=VAL1 KEY=VAL2 cmd` — single `env` prefix, not nested
# Always inject WORKTREE_PATH so the prompt can reference it and scripts/gh-lars work
# with the correct repo root regardless of CWD.
ENV_CMD=(env "WORKTREE_PATH=${WORKTREE}" "REPO_ROOT=${REPO_ROOT}")
for kv in "${ENV_VARS[@]+"${ENV_VARS[@]}"}"; do
    ENV_CMD+=("$kv")
done

# Expand env vars inside the prompt file so ${ISSUE_NUMBER}, ${PR_NUMBER}, etc. are
# substituted before being sent to claude as the user message.
# Falls back to raw cat if envsubst is unavailable (claude can still read env vars directly).
if command -v envsubst &>/dev/null; then
    PROMPT_CONTENT="$(
        # Export all --env KEY=VAL pairs plus injected vars into a subshell, then envsubst
        (
            export WORKTREE_PATH="$WORKTREE" REPO_ROOT="$REPO_ROOT"
            for kv in "${ENV_VARS[@]+"${ENV_VARS[@]}"}"; do
                export "${kv?}"
            done
            envsubst < "$PROMPT_FILE"
        )
    )"
else
    PROMPT_CONTENT="$(cat "$PROMPT_FILE")"
fi

# Invoke claude -p (non-interactive) with CWD = worktree so git ops target
# the correct branch, not whatever branch the main checkout happens to be on.
TMPOUT="$(mktemp)"
trap 'rm -f "$TMPOUT"' EXIT

set +e
# Run claude from the worktree directory so git operations (commit, push, branch)
# target the worktree's branch, not whatever branch the main checkout is on.
(cd "$WORKTREE" && "${ENV_CMD[@]}" "$CLAUDE_BIN" \
    -p "$PROMPT_CONTENT" \
    --model "$MODEL" \
    --add-dir "$WORKTREE" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep,MultiEdit" \
    --allow-dangerously-skip-permissions \
    --output-format stream-json \
    --verbose \
    ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} \
    2>&1) | tee "$TMPOUT"
# Capture exit code from the subshell (left side of pipe); tee always exits 0
EXIT_CODE=${PIPESTATUS[0]}
set -e

# Parse token usage from stream-json output
INPUT_TOKENS=0
OUTPUT_TOKENS=0
if command -v python3 &>/dev/null; then
    read -r INPUT_TOKENS OUTPUT_TOKENS < <(python3 - "$TMPOUT" <<'PYEOF'
import sys, json

inp_total = 0
out_total = 0
try:
    with open(sys.argv[1]) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage") or (obj.get("message") or {}).get("usage") or {}
            inp_total += usage.get("input_tokens", 0)
            out_total += usage.get("output_tokens", 0)
except Exception:
    pass
print(inp_total, out_total)
PYEOF
    )
fi

# Append delta to usage log
mkdir -p "$(dirname "$USAGE_LOG")"
printf '{"ts":"%s","model":"%s","label":"%s","input_tokens":%d,"output_tokens":%d,"exit_code":%d}\n' \
    "$START_TS" "$MODEL" "$LOG_LABEL" "$INPUT_TOKENS" "$OUTPUT_TOKENS" "$EXIT_CODE" \
    >> "$USAGE_LOG"

exit "$EXIT_CODE"
