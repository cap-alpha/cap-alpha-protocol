#!/usr/bin/env bash
# monitor_pr_threads.sh — scan open automation-app PRs for unresolved review threads.
#
# Prints a CHECKPOINT line per-PR (and one summary) and appends a JSON event to
# .claude/usage_log.jsonl so we can chart "unresolved-thread-minutes" over time.
#
# Usage:
#   scripts/monitor_pr_threads.sh           # run standalone
#   scripts/monitor_pr_threads.sh --quiet   # suppress per-PR output (cron-friendly)
#
# Exit codes:
#   0 — ran successfully (even if unresolved threads exist)
#   1 — script error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"

# Resolve usage_log path — lives in the main checkout's .claude/ dir.
_GIT_COMMON="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null || true)"
case "$_GIT_COMMON" in
  /*) MAIN_ROOT="$(dirname "$_GIT_COMMON")" ;;
  *)  MAIN_ROOT="$(cd "$SCRIPT_DIR/$_GIT_COMMON/.." && pwd)" ;;
esac
USAGE_LOG="${MAIN_ROOT}/.claude/usage_log.jsonl"

GH_LARS="${SCRIPT_DIR}/gh-lars"
OWNER="cap-alpha"
REPO="cap-alpha-protocol"
APP_AUTHOR="app/cap-alpha-workflow-automation"

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log() { [[ $QUIET -eq 0 ]] && echo "$*" || true; }

# ---------------------------------------------------------------------------
# 1. List open PRs authored by the automation app
# ---------------------------------------------------------------------------
PR_JSON="$("$GH_LARS" pr list \
  --author "$APP_AUTHOR" \
  --state open \
  --json number,title,createdAt \
  2>/dev/null)"

PR_COUNT="$(echo "$PR_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")"

if [[ "$PR_COUNT" -eq 0 ]]; then
  log "[CHECKPOINT] no open PRs by ${APP_AUTHOR} — nothing to scan"
  echo "{\"event\":\"thread_monitor\",\"ts\":\"$(now_iso)\",\"open_prs\":0,\"unresolved_prs\":0,\"total_unresolved_threads\":0}" >> "$USAGE_LOG"
  exit 0
fi

log "[CHECKPOINT] scanning ${PR_COUNT} open PR(s) by ${APP_AUTHOR} for unresolved threads..."

# ---------------------------------------------------------------------------
# 2. For each PR fetch unresolved review threads via GraphQL
# ---------------------------------------------------------------------------
total_unresolved=0
unresolved_pr_count=0

while IFS= read -r pr_number; do
  [[ -z "$pr_number" ]] && continue

  # Fetch reviewThreads
  thread_json="$("$GH_LARS" api graphql \
    -f query='
query($owner:String!,$repo:String!,$pr:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$pr){
      reviewThreads(first:50){
        nodes{ isResolved createdAt comments(first:1){ nodes{ body } } }
      }
    }
  }
}' \
    -f owner="$OWNER" \
    -f repo="$REPO" \
    -F pr="$pr_number" \
    2>/dev/null)"

  # Parse: count unresolved, compute oldest age in minutes
  read -r unresolved_count oldest_age_min < <(echo "$thread_json" | python3 - <<'PYEOF'
import sys, json
from datetime import datetime, timezone

data = json.load(sys.stdin)
nodes = (data.get("data") or {}) \
            .get("repository", {}) \
            .get("pullRequest", {}) \
            .get("reviewThreads", {}) \
            .get("nodes", [])

unresolved = [n for n in nodes if not n.get("isResolved", True)]
count = len(unresolved)

if count == 0:
    print("0 0")
else:
    now = datetime.now(timezone.utc)
    ages = []
    for n in unresolved:
        created = n.get("createdAt", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                ages.append(int((now - dt).total_seconds() / 60))
            except ValueError:
                pass
    oldest = max(ages) if ages else 0
    print(f"{count} {oldest}")
PYEOF
)

  if [[ "$unresolved_count" -gt 0 ]]; then
    unresolved_pr_count=$((unresolved_pr_count + 1))
    total_unresolved=$((total_unresolved + unresolved_count))
    log "[CHECKPOINT] PR #${pr_number} has ${unresolved_count} unresolved thread(s), oldest age=${oldest_age_min}min"
  else
    log "[CHECKPOINT] PR #${pr_number} — 0 unresolved threads"
  fi

done < <(echo "$PR_JSON" | python3 -c "
import sys, json
for pr in json.load(sys.stdin):
    print(pr['number'])
")

# ---------------------------------------------------------------------------
# 3. Summary line
# ---------------------------------------------------------------------------
if [[ "$total_unresolved" -eq 0 ]]; then
  log "[CHECKPOINT] all open PRs have 0 unresolved threads"
else
  log "[CHECKPOINT] ${unresolved_pr_count} PR(s) have unresolved threads; total unresolved=${total_unresolved}"
fi

# ---------------------------------------------------------------------------
# 4. Append to usage_log.jsonl
# ---------------------------------------------------------------------------
echo "{\"event\":\"thread_monitor\",\"ts\":\"$(now_iso)\",\"open_prs\":${PR_COUNT},\"unresolved_prs\":${unresolved_pr_count},\"total_unresolved_threads\":${total_unresolved}}" >> "$USAGE_LOG"
