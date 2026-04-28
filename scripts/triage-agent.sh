#!/usr/bin/env bash
# triage-agent.sh — Autonomous hourly issue/PR triage agent
#
# Runs every hour (via launchd or cron). For each open GitHub issue:
#   • If not claimed and has clear acceptance criteria → claims it + spawns subagent
#   • If ambiguous / needs clarification → logs a notification
# Also flags open PRs with unaddressed review comments > 6 hours old.
#
# TODO: Slack notification — set SLACK_WEBHOOK_URL env var and uncomment:
# curl -s -X POST "$SLACK_WEBHOOK_URL" -H 'Content-type: application/json' \
#   --data "{\"text\":\"🔔 Needs clarification: #$issue_number — $title\"}"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="${REPO_ROOT}/.agent"
GH_LARS="${REPO_ROOT}/scripts/gh-lars"
NOTIFICATIONS="${REPO_ROOT}/.claude/notifications.md"
AGENT_ID="triage-agent-$(hostname -s)-$$"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ── helpers ───────────────────────────────────────────────────────────────────

log() { echo "[$(ts)] $*"; }

notify() {
    local issue_number="$1" title="$2" why_blocked="$3" question="$4"

    # Append to persistent human-readable log
    mkdir -p "$(dirname "$NOTIFICATIONS")"
    {
        echo ""
        echo "## [$(ts)] Needs clarification: Issue #${issue_number} — ${title}"
        echo "**Why blocked:** ${why_blocked}"
        echo "**Question:** ${question}"
    } >> "$NOTIFICATIONS"

    # Print visibly to stdout (Claude Code surfaces these)
    echo ""
    echo "🔔 NEEDS YOUR INPUT: Issue #${issue_number} — ${title}"
    echo "   Question: ${question}"
    echo ""
}

# Check if an issue is already claimed in .agent/current.md
is_claimed() {
    local issue_number="$1"
    grep -q "^issue:${issue_number}" "${AGENT_DIR}/current.md" 2>/dev/null || false
}

# Heuristic: does the issue body contain enough info to work autonomously?
# Returns 0 (true) if autonomous work is viable, 1 if clarification needed.
# Also sets BLOCK_REASON and BLOCK_QUESTION globals when returning 1.
BLOCK_REASON=""
BLOCK_QUESTION=""

can_work_autonomously() {
    local body="$1"
    local labels="$2"

    # Clear signals that we need clarification
    local ambiguous_phrases=(
        "TBD" "TODO: clarify" "?" "open question" "discussion needed"
        "what should" "which approach" "unclear" "not sure" "to be determined"
        "needs design" "needs discussion" "RFC"
    )

    # Required signals for autonomous work
    # At least one of: acceptance criteria, "should", "must", clear feature description
    local has_criteria=false
    if echo "$body" | grep -qi "acceptance criteria\|should\|must\|requirement\|implement\|add\|fix\|update\|create"; then
        has_criteria=true
    fi

    # Check for ambiguity
    for phrase in "${ambiguous_phrases[@]}"; do
        if echo "$body" | grep -qi "$phrase"; then
            BLOCK_REASON="Issue body contains ambiguous phrase: '${phrase}'"
            BLOCK_QUESTION="Is the scope clear enough to proceed? Specifically: what exact output should this produce?"
            return 1
        fi
    done

    # If the body is very short (< 50 chars), likely needs more info
    local body_len=${#body}
    if [ "$body_len" -lt 50 ]; then
        BLOCK_REASON="Issue body is too short (${body_len} chars) to infer acceptance criteria"
        BLOCK_QUESTION="What are the acceptance criteria for this issue?"
        return 1
    fi

    # Check for question-only labels that signal discussion
    if echo "$labels" | grep -qi "question\|discussion\|needs-design\|wontfix\|invalid\|help wanted"; then
        BLOCK_REASON="Issue has a label indicating it needs human input (labels: ${labels})"
        BLOCK_QUESTION="This is marked as a discussion/question issue. Can you clarify the expected implementation?"
        return 1
    fi

    if [ "$has_criteria" = "false" ]; then
        BLOCK_REASON="Cannot identify acceptance criteria in issue body"
        BLOCK_QUESTION="What should 'done' look like for this issue?"
        return 1
    fi

    return 0
}

# ── Part 1: Triage open issues ────────────────────────────────────────────────

triage_issues() {
    log "Fetching open issues..."

    local issues
    issues=$("$GH_LARS" issue list \
        --state open \
        --limit 50 \
        --json number,title,body,labels,assignees \
        2>/dev/null) || {
        log "WARNING: Could not fetch issues (gh may not be authenticated)"
        return
    }

    local issue_count
    issue_count=$(echo "$issues" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
    log "Found ${issue_count} open issues"

    echo "$issues" | python3 - <<'PYEOF'
import sys, json, os, subprocess, shlex

data = json.load(sys.stdin)

for issue in data:
    number = issue["number"]
    title  = issue.get("title", "")
    body   = issue.get("body", "") or ""
    labels = ", ".join(l["name"] for l in issue.get("labels", []))
    assignees = [a["login"] for a in issue.get("assignees", [])]

    print(f"ISSUE {number} '{title}' LABELS='{labels}' BODY_LEN={len(body)}")
PYEOF

    # Process each issue via shell
    while IFS= read -r line; do
        local number title labels body_len
        number=$(echo "$line"  | grep -oP '(?<=ISSUE )\d+')
        title=$(echo "$line"   | grep -oP "(?<=').*(?=' LABELS=)")
        labels=$(echo "$line"  | grep -oP "(?<=LABELS=').*(?=' BODY_LEN=)")
        body_len=$(echo "$line"| grep -oP "(?<=BODY_LEN=)\d+")

        [ -z "$number" ] && continue

        log "Checking issue #${number}: ${title}"

        # Skip if already claimed
        if is_claimed "$number"; then
            log "  → Already claimed, skipping"
            continue
        fi

        # Fetch the full body for heuristic check
        local body
        body=$("$GH_LARS" issue view "$number" --json body --jq '.body' 2>/dev/null || echo "")

        BLOCK_REASON=""
        BLOCK_QUESTION=""
        if can_work_autonomously "$body" "$labels"; then
            log "  → Can work autonomously — claiming and spawning subagent"
            if ALLOW_MAIN_CHECKOUT=1 "${AGENT_DIR}/claim.sh" claim "issue:${number}" "$AGENT_ID" 2>/dev/null; then
                spawn_subagent "$number" "$title" "$body"
            else
                log "  → Could not claim issue:${number} (race condition), skipping"
            fi
        else
            log "  → Needs clarification: ${BLOCK_REASON}"
            notify "$number" "$title" "$BLOCK_REASON" "$BLOCK_QUESTION"
        fi

    done < <(echo "$issues" | python3 - <<'PYEOF2'
import sys, json
data = json.load(sys.stdin)
for issue in data:
    number = issue["number"]
    title  = (issue.get("title", "") or "").replace("'", " ")
    body   = issue.get("body", "") or ""
    labels = ", ".join(l["name"] for l in issue.get("labels", []))
    print(f"ISSUE {number} '{title}' LABELS='{labels}' BODY_LEN={len(body)}")
PYEOF2
)
}

spawn_subagent() {
    local number="$1" title="$2" body="$3"
    log "  → Spawning subagent for issue #${number}: ${title}"

    # Create a worktree for this issue
    local branch="feat/${number}-auto-triage"
    local worktree_path="${REPO_ROOT}/.claude/worktrees/auto-issue-${number}"

    if git -C "$REPO_ROOT" worktree add "$worktree_path" -b "$branch" 2>/dev/null; then
        log "  → Worktree created at ${worktree_path}"
        # Spawn Claude Code subagent asynchronously
        # In production this would invoke: claude --worktree "$worktree_path" "Work on issue #${number}: ${title}"
        # For now, log the intent and let the operator trigger manually.
        log "  → SPAWN: claude --cwd '${worktree_path}' 'Work on GitHub issue #${number}: ${title}. Follow CLAUDE.md.'"
        echo "  SUBAGENT_SPAWN issue:${number} branch:${branch} worktree:${worktree_path}"
    else
        log "  → Worktree already exists or branch conflict for issue #${number}, skipping spawn"
    fi
}

# ── Part 2: Triage open PRs with stale review comments ───────────────────────

triage_prs() {
    log "Fetching open PRs..."

    local prs
    prs=$("$GH_LARS" pr list \
        --state open \
        --limit 30 \
        --json number,title,reviewDecision,reviews,createdAt \
        2>/dev/null) || {
        log "WARNING: Could not fetch PRs"
        return
    }

    local pr_count
    pr_count=$(echo "$prs" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
    log "Found ${pr_count} open PRs"

    local six_hours_ago
    six_hours_ago=$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u --date="6 hours ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")

    # Check each PR for unresolved review comments older than 6 hours
    echo "$prs" | python3 - "$six_hours_ago" "$NOTIFICATIONS" "$GH_LARS" <<'PYEOF'
import sys, json, subprocess
from datetime import datetime, timezone

data = json.load(sys.stdin)
six_hours_ago_str = sys.argv[1]
notifications_file = sys.argv[2]
gh_lars = sys.argv[3]

def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.rstrip("Z")).replace(tzinfo=timezone.utc)
    except Exception:
        return None

six_hours_ago = parse_dt(six_hours_ago_str)

for pr in data:
    number = pr["number"]
    title  = pr.get("title", "")
    reviews = pr.get("reviews", []) or []

    # Find review comments that request changes and are older than 6h
    stale_reviews = []
    for r in reviews:
        if r.get("state") == "CHANGES_REQUESTED":
            submitted = parse_dt(r.get("submittedAt", ""))
            if submitted and six_hours_ago and submitted < six_hours_ago:
                reviewer = r.get("author", {}).get("login", "unknown")
                stale_reviews.append(f"{reviewer} ({r.get('submittedAt','')})")

    if stale_reviews:
        print(f"STALE_PR {number} '{title}' REVIEWERS={','.join(stale_reviews)}")
PYEOF

    # Log stale PRs as notifications
    while IFS= read -r line; do
        [[ "$line" != STALE_PR* ]] && continue
        local number title
        number=$(echo "$line" | grep -oP '(?<=STALE_PR )\d+')
        title=$(echo "$line"  | grep -oP "(?<=').*(?=' REVIEWERS=)")
        [ -z "$number" ] && continue

        local url
        url=$("$GH_LARS" pr view "$number" --json url --jq '.url' 2>/dev/null || echo "")
        local why="PR #${number} has unaddressed review comments requesting changes older than 6 hours"
        local question="Please review the change requests at ${url} and either address them or mark them as resolved."

        mkdir -p "$(dirname "$NOTIFICATIONS")"
        {
            echo ""
            echo "## [$(ts)] Stale review on PR #${number} — ${title}"
            echo "**Why blocked:** ${why}"
            echo "**Action needed:** ${question}"
        } >> "$NOTIFICATIONS"

        echo ""
        echo "🔔 NEEDS YOUR INPUT: PR #${number} — ${title}"
        echo "   Stale review comments older than 6h. URL: ${url}"
        echo ""

    done < <(echo "$prs" | python3 - "$six_hours_ago" <<'PYEOF2'
import sys, json
from datetime import datetime, timezone

data = json.load(sys.stdin)
six_hours_ago_str = sys.argv[1]

def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.rstrip("Z")).replace(tzinfo=timezone.utc)
    except Exception:
        return None

six_hours_ago = parse_dt(six_hours_ago_str)

for pr in data:
    number = pr["number"]
    title  = (pr.get("title", "") or "").replace("'", " ")
    reviews = pr.get("reviews", []) or []
    stale_reviews = []
    for r in reviews:
        if r.get("state") == "CHANGES_REQUESTED":
            submitted = parse_dt(r.get("submittedAt", ""))
            if submitted and six_hours_ago and submitted < six_hours_ago:
                reviewer = (r.get("author") or {}).get("login", "unknown")
                stale_reviews.append(f"{reviewer}({r.get('submittedAt','')})")
    if stale_reviews:
        print(f"STALE_PR {number} '{title}' REVIEWERS={','.join(stale_reviews)}")
PYEOF2
)
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    log "=== Triage agent starting ==="
    log "Repo: ${REPO_ROOT}"
    log "Notifications: ${NOTIFICATIONS}"

    triage_issues
    triage_prs

    log "=== Triage agent complete ==="

    if [ -f "$NOTIFICATIONS" ]; then
        local pending
        pending=$(grep -c "^## \[" "$NOTIFICATIONS" 2>/dev/null || echo 0)
        log "Notification log has ${pending} entries total: ${NOTIFICATIONS}"
    fi
}

main "$@"
