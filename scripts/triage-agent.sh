#!/usr/bin/env bash
# triage-agent.sh — Autonomous triage: dispatch issues, fix PR threads, fix lint, investigate CI.
# Invoked by launchd (com.capalpha.triage-agent) every 10 minutes.
#
# Flags:
#   --dry-run   Print what would be dispatched; do not invoke claude or claim locks.

set -euo pipefail
START_TIME=$(date +%s)

PERSONAS_FILE="$(dirname "${BASH_SOURCE[0]}")/../.env.personas"
if [ -f "$PERSONAS_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; source "$PERSONAS_FILE"; set +a
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="${REPO_ROOT}/.agent"
GH_LARS="${REPO_ROOT}/scripts/gh-lars"
DISPATCH="${REPO_ROOT}/scripts/dispatch-claude.sh"
PROMPTS_DIR="${REPO_ROOT}/scripts/prompts"
NOTIFICATIONS="${REPO_ROOT}/.claude/notifications.md"
USAGE_LOG="${REPO_ROOT}/.claude/usage_log.jsonl"
GATE_FILE="${REPO_ROOT}/.claude/current_gate.txt"
CLAUDE_BIN="${CLAUDE_BIN:-/opt/homebrew/bin/claude}"
AGENT_ID="triage-agent-$(hostname -s)-$$"

# Concurrency cap: max parallel subagents per run
CONCURRENCY_CAP=4
# Claude Max throttle window: 50M output tokens per 5h; pause at 80%
QUOTA_OUTPUT_LIMIT=$(( 50000000 * 80 / 100 ))   # 40M output tokens per 5h
QUOTA_WINDOW_HOURS=5

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

ts()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] $*"; }

get_recent_token_usage() {
    local window_hours="${1:-5}"
    [[ ! -f "$USAGE_LOG" ]] && echo "0" && return 0
    python3 - "$USAGE_LOG" "$window_hours" <<'PYEOF'
import sys, json
from datetime import datetime, timezone, timedelta

log_path = sys.argv[1]
window_hours = int(sys.argv[2])
cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

total_input = 0
total_output = 0
try:
    with open(log_path) as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                ts_str = obj.get("ts", "")
                ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    total_input += obj.get("input_tokens", 0)
                    total_output += obj.get("output_tokens", 0)
            except Exception:
                pass
except FileNotFoundError:
    pass
print(f"input={total_input} output={total_output}")
PYEOF
}


# ── Quota awareness ───────────────────────────────────────────────────────────

check_quota() {
    [[ ! -f "$USAGE_LOG" ]] && return 0

    local cutoff_ts
    cutoff_ts=$(python3 -c "
from datetime import datetime, timezone, timedelta
cutoff = datetime.now(timezone.utc) - timedelta(hours=${QUOTA_WINDOW_HOURS})
print(cutoff.strftime('%Y-%m-%dT%H:%M:%SZ'))
")

    local recent_output_tokens
    recent_output_tokens=$(python3 - "$USAGE_LOG" "$cutoff_ts" <<'PYEOF'
import sys, json
from datetime import datetime, timezone

log_path = sys.argv[1]
cutoff_str = sys.argv[2]
cutoff = datetime.fromisoformat(cutoff_str.rstrip("Z")).replace(tzinfo=timezone.utc)

total = 0
try:
    with open(log_path) as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                ts_str = obj.get("ts", "")
                ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    total += obj.get("output_tokens", 0)
            except Exception:
                pass
except FileNotFoundError:
    pass
print(total)
PYEOF
    )

    if (( recent_output_tokens >= QUOTA_OUTPUT_LIMIT )); then
        log "QUOTA EXCEEDED: ${recent_output_tokens} output tokens in last ${QUOTA_WINDOW_HOURS}h (limit: ${QUOTA_OUTPUT_LIMIT}). Pausing run."
        slack_alert "Triage agent quota pause: ${recent_output_tokens} output tokens in last ${QUOTA_WINDOW_HOURS}h. Next run in ~10min."
        return 1
    fi

    log "Quota OK: ${recent_output_tokens} output tokens in last ${QUOTA_WINDOW_HOURS}h (limit: ${QUOTA_OUTPUT_LIMIT})"
    return 0
}

# ── Slack escalation ─────────────────────────────────────────────────────────

slack_alert() {
    local message="$1"
    if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
        local payload
        payload=$(python3 -c "import json,sys; print(json.dumps({'channel': sys.argv[1], 'text': sys.argv[2]}))" \
            "${SLACK_CHANNEL:-#cap-alpha-protocol}" \
            "$message")
        curl -s -X POST "$SLACK_WEBHOOK_URL" -H 'Content-type: application/json' --data "$payload" > /dev/null || true
    fi
}

notify() {
    local issue_number="$1" title="$2" why_blocked="$3" question="$4"
    mkdir -p "$(dirname "$NOTIFICATIONS")"
    {
        echo ""
        echo "## [$(ts)] Needs clarification: Issue #${issue_number} — ${title}"
        echo "**Why blocked:** ${why_blocked}"
        echo "**Question:** ${question}"
    } >> "$NOTIFICATIONS"
    log "ESCALATE issue #${issue_number}: ${why_blocked}"
    slack_alert "Needs your input: Issue #${issue_number} — ${title}\n>${question}"
}

# ── Claim helper ─────────────────────────────────────────────────────────────

is_claimed() {
    grep -q "^issue:${1}" "${AGENT_DIR}/current.md" 2>/dev/null
}

is_pr_claimed() {
    grep -q "^pr:${1}" "${AGENT_DIR}/current.md" 2>/dev/null
}

claim_resource() {
    local resource="$1"
    ALLOW_MAIN_CHECKOUT=1 "${AGENT_DIR}/claim.sh" claim "$resource" "$AGENT_ID" 2>/dev/null
}

# ── Autonomy classifier (salvaged from original script) ───────────────────────

BLOCK_REASON=""
BLOCK_QUESTION=""

can_work_autonomously() {
    local body="$1"
    local labels="$2"

    local ambiguous_phrases=(
        "TBD" "TODO: clarify" "open question" "discussion needed"
        "what should" "which approach" "unclear" "not sure" "to be determined"
        "needs design" "needs discussion" "RFC"
    )

    local has_criteria=false
    if echo "$body" | grep -qi "acceptance criteria\|should\|must\|requirement\|implement\|add\|fix\|update\|create"; then
        has_criteria=true
    fi

    for phrase in "${ambiguous_phrases[@]}"; do
        if echo "$body" | grep -qi "$phrase"; then
            BLOCK_REASON="Issue body contains ambiguous phrase: '${phrase}'"
            BLOCK_QUESTION="Is the scope clear enough to proceed? What exact output should this produce?"
            return 1
        fi
    done

    local body_len=${#body}
    if [ "$body_len" -lt 50 ]; then
        BLOCK_REASON="Issue body too short (${body_len} chars)"
        BLOCK_QUESTION="What are the acceptance criteria?"
        return 1
    fi

    if echo "$labels" | grep -qi "question\|discussion\|needs-design\|wontfix\|invalid"; then
        BLOCK_REASON="Label indicates human input needed (${labels})"
        BLOCK_QUESTION="Can you clarify the expected implementation?"
        return 1
    fi

    if [ "$has_criteria" = "false" ]; then
        BLOCK_REASON="Cannot identify acceptance criteria"
        BLOCK_QUESTION="What should 'done' look like?"
        return 1
    fi

    return 0
}

# ── Concurrency tracker ───────────────────────────────────────────────────────

declare -a BACKGROUND_PIDS=()

wait_if_at_cap() {
    while (( ${#BACKGROUND_PIDS[@]} >= CONCURRENCY_CAP )); do
        # Wait for any one job to finish
        local new_pids=()
        for pid in "${BACKGROUND_PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                new_pids+=("$pid")
            fi
        done
        BACKGROUND_PIDS=("${new_pids[@]:-}")
        if (( ${#BACKGROUND_PIDS[@]} >= CONCURRENCY_CAP )); then
            sleep 2
        fi
    done
}

wait_all() {
    for pid in "${BACKGROUND_PIDS[@]:-}"; do
        wait "$pid" 2>/dev/null || true
    done
}

spawn_background() {
    wait_if_at_cap
    "$@" &
    BACKGROUND_PIDS+=($!)
}

# ── Gate filter ───────────────────────────────────────────────────────────────

current_gate() {
    if [[ -f "$GATE_FILE" ]]; then
        tr -d '[:space:]' < "$GATE_FILE"
    else
        echo "0"
    fi
}

issue_gate() {
    local title="$1"
    # Match [Gate N] or [Gate N / WO-NNN]
    if [[ "$title" =~ \[Gate[[:space:]]+([0-9]+) ]]; then
        echo "${BASH_REMATCH[1]}"
    else
        echo "-1"   # Not a gated issue — skip
    fi
}

# ── Issue dispatch ────────────────────────────────────────────────────────────

dispatch_issue() {
    local number="$1" title="$2" body="$3"
    local branch="feat/${number}-auto"
    local worktree_path="${REPO_ROOT}/.claude/worktrees/auto-issue-${number}"

    if $DRY_RUN; then
        log "would dispatch: issue #${number} via Sonnet → ${worktree_path}"
        return
    fi

    log "DISPATCH issue #${number}: ${title}"

    # Remove stale worktree if present without a live branch
    if [[ -d "$worktree_path" ]]; then
        log "  Worktree already exists at ${worktree_path}, skipping"
        return
    fi

    git -C "$REPO_ROOT" fetch origin main --quiet 2>/dev/null || true
    git -C "$REPO_ROOT" worktree add "$worktree_path" -b "$branch" origin/main 2>/dev/null || {
        log "  Branch conflict for #${number}, skipping"
        return
    }

    spawn_background "$DISPATCH" \
        --model "claude-sonnet-4-6" \
        --prompt-file "${PROMPTS_DIR}/issue-work.md" \
        --worktree "$worktree_path" \
        --label "issue-${number}" \
        --env "ISSUE_NUMBER=${number}" \
        --env "ISSUE_TITLE=${title}" \
        --env "ISSUE_BODY=${body}" \
        --env "AGENT_ID=${AGENT_ID}"
}

triage_issues() {
    local gate dispatched_count=0
    gate="$(current_gate)"
    log "ISSUES gate=${gate}"

    local issues
    issues=$("$GH_LARS" issue list \
        --state open \
        --limit 50 \
        --json number,title,body,labels,assignees \
        2>/dev/null) || {
        log "WARN: issue fetch failed"
        return 0
    }

    local issue_count
    issue_count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" <<< "$issues" 2>/dev/null || echo 0)
    log "issues found=${issue_count}"

    while IFS=$'\t' read -r number title labels body; do
        [[ -z "$number" ]] && continue

        local ig
        ig=$(issue_gate "$title")
        if (( ig < 0 )); then
            log "  #${number} not gated, skipping"
            continue
        fi
        if (( ig > gate )); then
            log "  #${number} gate ${ig} > current ${gate}, skipping"
            continue
        fi

        if is_claimed "$number"; then
            log "  #${number} already claimed, skipping"
            continue
        fi

        BLOCK_REASON=""
        BLOCK_QUESTION=""
        if can_work_autonomously "$body" "$labels"; then
            if $DRY_RUN; then
                log "would dispatch: issue #${number} '${title}'"
            else
                if claim_resource "issue:${number}"; then
                    dispatch_issue "$number" "$title" "$body"
                else
                    log "  Could not claim issue:${number} (race), skipping"
                fi
            fi
        else
            notify "$number" "$title" "$BLOCK_REASON" "$BLOCK_QUESTION"
        fi

    done < <(python3 -c '
import sys, json
raw = open(sys.argv[1]).read()
data = json.loads(raw)
for issue in data:
    number = issue.get("number","")
    title  = (issue.get("title","") or "").replace("\t"," ").replace("\n"," ")
    body   = (issue.get("body","") or "").replace("\t"," ").replace("\n"," ")[:2000]
    labels = ", ".join(l["name"] for l in (issue.get("labels") or []))
    print(f"{number}\t{title}\t{labels}\t{body}")
' <(echo "$issues"))
}

# ── PR triage ─────────────────────────────────────────────────────────────────

dispatch_pr_copilot() {
    local pr_number="$1"
    local worktree_path="${REPO_ROOT}/.claude/worktrees/auto-pr-copilot-${pr_number}"

    if $DRY_RUN; then
        log "would dispatch: PR #${pr_number} copilot-fix via Sonnet"
        return
    fi

    log "Dispatching Copilot fix for PR #${pr_number}"
    [[ -d "$worktree_path" ]] && { log "  Copilot worktree already exists, skipping"; return; }

    git -C "$REPO_ROOT" worktree add --detach "$worktree_path" 2>/dev/null || {
        log "  Could not create worktree for copilot fix on PR #${pr_number}"
        return
    }

    spawn_background "$DISPATCH" \
        --model "claude-sonnet-4-6" \
        --prompt-file "${PROMPTS_DIR}/copilot-fix.md" \
        --worktree "$worktree_path" \
        --label "pr-copilot-${pr_number}" \
        --env "PR_NUMBER=${pr_number}" \
        --env "AGENT_ID=${AGENT_ID}"
}

dispatch_pr_lint() {
    local pr_number="$1"
    local worktree_path="${REPO_ROOT}/.claude/worktrees/auto-pr-lint-${pr_number}"

    if $DRY_RUN; then
        log "would dispatch: PR #${pr_number} lint-fix via Haiku"
        return
    fi

    log "Dispatching lint fix for PR #${pr_number}"
    [[ -d "$worktree_path" ]] && { log "  Lint worktree already exists, skipping"; return; }

    git -C "$REPO_ROOT" worktree add --detach "$worktree_path" 2>/dev/null || {
        log "  Could not create worktree for lint fix on PR #${pr_number}"
        return
    }

    spawn_background "$DISPATCH" \
        --model "claude-haiku-4-5-20251001" \
        --prompt-file "${PROMPTS_DIR}/lint-fix.md" \
        --worktree "$worktree_path" \
        --label "pr-lint-${pr_number}" \
        --env "PR_NUMBER=${pr_number}" \
        --env "AGENT_ID=${AGENT_ID}"
}

dispatch_pr_ci() {
    local pr_number="$1" failing_check="$2"
    local worktree_path="${REPO_ROOT}/.claude/worktrees/auto-pr-ci-${pr_number}"

    if $DRY_RUN; then
        log "would dispatch: PR #${pr_number} ci-investigate (${failing_check}) via Sonnet"
        return
    fi

    log "Dispatching CI investigation for PR #${pr_number} (${failing_check})"
    [[ -d "$worktree_path" ]] && { log "  CI worktree already exists, skipping"; return; }

    git -C "$REPO_ROOT" worktree add --detach "$worktree_path" 2>/dev/null || {
        log "  Could not create worktree for CI investigate on PR #${pr_number}"
        return
    }

    spawn_background "$DISPATCH" \
        --model "claude-sonnet-4-6" \
        --prompt-file "${PROMPTS_DIR}/ci-investigate.md" \
        --worktree "$worktree_path" \
        --label "pr-ci-${pr_number}" \
        --env "PR_NUMBER=${pr_number}" \
        --env "FAILING_CHECK=${failing_check}" \
        --env "AGENT_ID=${AGENT_ID}"
}

triage_prs() {
    local prs
    log "PRS"

    prs=$("$GH_LARS" pr list \
        --state open \
        --limit 30 \
        --json number,title,headRefName,statusCheckRollup,reviews \
        2>/dev/null) || {
        log "WARN: pr fetch failed"
        return 0
    }

    local pr_count
    pr_count=$(python3 -c "import sys,json; print(len(json.load(sys.stdin)))" <<< "$prs" 2>/dev/null || echo 0)
    log "prs found=${pr_count}"

    # Process each PR via python — output tab-separated action lines
    while IFS=$'\t' read -r action pr_number extra; do
        [[ -z "$pr_number" ]] && continue

        case "$action" in
            COPILOT)
                if ! is_pr_claimed "${pr_number}-copilot"; then
                    if claim_resource "pr:${pr_number}-copilot"; then
                        dispatch_pr_copilot "$pr_number"
                    else
                        log "  Could not claim pr:${pr_number}-copilot (race), skipping"
                    fi
                fi
                ;;
            LINT)
                if ! is_pr_claimed "${pr_number}-lint"; then
                    if claim_resource "pr:${pr_number}-lint"; then
                        dispatch_pr_lint "$pr_number"
                    else
                        log "  Could not claim pr:${pr_number}-lint (race), skipping"
                    fi
                fi
                ;;
            CI)
                if ! is_pr_claimed "${pr_number}-ci"; then
                    if claim_resource "pr:${pr_number}-ci"; then
                        dispatch_pr_ci "$pr_number" "$extra"
                    else
                        log "  Could not claim pr:${pr_number}-ci (race), skipping"
                    fi
                fi
                ;;
        esac

    done < <(python3 -c '
import sys, json

data = json.loads(open(sys.argv[1]).read())

for pr in data:
    number = pr.get("number","")

    # Detect PRs needing review fixes — use CHANGES_REQUESTED as proxy
    reviews = pr.get("reviews") or []
    has_changes_requested = any(r.get("state") == "CHANGES_REQUESTED" for r in reviews)
    if has_changes_requested:
        print(f"COPILOT\t{number}\t")
        continue  # prioritize copilot fix; lint/CI can wait

    # CI status
    checks = pr.get("statusCheckRollup") or []
    lint_failing = False
    ci_failing_name = ""
    for check in checks:
        name = (check.get("name") or check.get("context") or "").lower()
        conclusion = (check.get("conclusion") or check.get("state") or "").upper()
        if conclusion in ("FAILURE", "TIMED_OUT", "ERROR"):
            if "lint" in name or "ruff" in name or "format" in name:
                lint_failing = True
            else:
                ci_failing_name = check.get("name") or check.get("context") or "unknown"

    if lint_failing:
        print(f"LINT\t{number}\t")
    elif ci_failing_name:
        print(f"CI\t{number}\t{ci_failing_name}")
' <(echo "$prs"))
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    local token_start
    token_start=$(get_recent_token_usage 5)

    log "START tokens=${token_start} dry=${DRY_RUN}"

    # Rate-limit guard: if gh-lars returns 403/429, we skip gracefully (done inside triage_* fns)
    # Quota check
    if ! $DRY_RUN; then
        check_quota || exit 0
    fi

    triage_issues
    triage_prs

    wait_all

    local END_TIME elapsed token_end
    END_TIME=$(date +%s)
    elapsed=$((END_TIME - START_TIME))
    token_end=$(get_recent_token_usage 5)

    log "DONE elapsed=${elapsed}s tokens=${token_end}"
}

main "$@"
