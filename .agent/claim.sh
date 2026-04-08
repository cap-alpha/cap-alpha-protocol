#!/bin/bash
# Agent coordination — race-condition safe via atomic mkdir locks
#
# POSIX guarantees mkdir is atomic: exactly one concurrent caller succeeds.
# Two agents racing to claim the same resource cannot both win.
#
# Usage:
#   .agent/claim.sh claim   <resource> <agent-id>   # claim; exits 1 if held
#   .agent/claim.sh release <resource> <agent-id>   # release your lock
#   .agent/claim.sh check   <resource>              # print owner or "free"
#   .agent/claim.sh status                          # list all active locks
#   .agent/claim.sh cleanup                         # remove locks older than STALE_MINUTES
#
# Resources use a namespace prefix:
#   issue:<n>   pr:<n>   file:<path>   branch:<name>
#
# Environment overrides:
#   STALE_MINUTES   — minutes before a lock is considered stale (default: 60)
#   LOG_RETAIN_DAYS — days of history to keep in activity.log (default: 7)

set -euo pipefail

# ── worktree guard ────────────────────────────────────────────────────────────
# claim/release in the main checkout is almost always a mistake — the lock
# system exists precisely because agents share the main repo, but actual
# work should happen in worktrees. Refuse unless explicitly overridden.
if [ "${1:-}" != "status" ] && [ "${1:-}" != "check" ] && [ "${ALLOW_MAIN_CHECKOUT:-0}" != "1" ]; then
    git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
    git_common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"
    if [ -n "$git_dir" ] && [ "$git_dir" = "$git_common_dir" ]; then
        cat >&2 <<'WTMSG'
✗ Refusing to claim/release from the main checkout.

This is a coordination footgun: the locks live in the main repo, but the
actual file edits should happen in an isolated worktree so concurrent agents
do not step on each other.

Move into a worktree first:
  git worktree add .claude/worktrees/<name> -b <branch>
  cd .claude/worktrees/<name>
  .agent/claim.sh claim issue:<n> <agent-id>

Override (not recommended) by setting:  ALLOW_MAIN_CHECKOUT=1
WTMSG
        exit 1
    fi
fi

AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCKS_DIR="${AGENT_DIR}/locks"
LOG="${AGENT_DIR}/activity.log"
STATUS_FILE="${AGENT_DIR}/current.md"
ROTATE_MARKER="${AGENT_DIR}/.last_rotate"

STALE_MINUTES="${STALE_MINUTES:-60}"
LOG_RETAIN_DAYS="${LOG_RETAIN_DAYS:-7}"

mkdir -p "$LOCKS_DIR"

# ── helpers ───────────────────────────────────────────────────────────────────

resource_to_dir() { echo "$1" | sed 's|[:/]|_|g'; }
ts()    { date -u +%Y-%m-%dT%H:%M:%SZ; }
epoch() { date -u +%s; }

log_action() {
    local action="$1" resource="$2" agent="$3"
    echo "$(ts) | ${agent} | ${action} | ${resource}" >> "$LOG"
}

# ── write_status ──────────────────────────────────────────────────────────────
# Atomically regenerate current.md from the live locks directory.
# mv is atomic on POSIX — readers always see a complete file.
write_status() {
    local now_epoch now_ts tmp
    now_epoch=$(epoch)
    now_ts=$(ts)
    tmp="${STATUS_FILE}.tmp.$$"

    {
        echo "# Agent Coordination — Current Status"
        echo "Last updated: ${now_ts}"
        echo ""

        local found=0
        for lock_dir in "${LOCKS_DIR}"/*/; do
            [ -d "$lock_dir" ] || continue
            [ -f "${lock_dir}/owner" ] || continue
            if [ "$found" -eq 0 ]; then
                printf '%-50s  %-32s  %s\n' "RESOURCE" "AGENT" "AGE"
                printf '%-50s  %-32s  %s\n' \
                    "--------------------------------------------------" \
                    "--------------------------------" "-------"
            fi
            found=1
            local lock_epoch lock_agent resource age_secs note=""
            lock_epoch=$(grep '^EPOCH=' "${lock_dir}/owner" | cut -d= -f2)
            lock_agent=$(grep '^AGENT=' "${lock_dir}/owner" | cut -d= -f2)
            resource=$(grep  '^RESOURCE=' "${lock_dir}/owner" | cut -d= -f2)
            age_secs=$(( now_epoch - lock_epoch ))
            [ "$age_secs" -ge $(( STALE_MINUTES * 60 )) ] && note="  *** STALE ***"
            printf '%-50s  %-32s  %ds%s\n' "$resource" "$lock_agent" "$age_secs" "$note"
        done

        [ "$found" -eq 0 ] && echo "(no active locks)"
    } > "$tmp"

    mv "$tmp" "$STATUS_FILE"
}

# ── rotate_log ────────────────────────────────────────────────────────────────
# Prune activity.log entries older than LOG_RETAIN_DAYS, runs at most weekly.
rotate_log() {
    local now_epoch week_secs last_rotate
    now_epoch=$(epoch)
    week_secs=$(( 7 * 24 * 3600 ))

    if [ -f "$ROTATE_MARKER" ]; then
        last_rotate=$(cat "$ROTATE_MARKER")
        [ $(( now_epoch - last_rotate )) -lt "$week_secs" ] && return 0
    fi

    local cutoff=$(( now_epoch - LOG_RETAIN_DAYS * 24 * 3600 ))
    local tmp="${LOG}.rotate.$$"

    python3 - "$LOG" "$cutoff" "$tmp" <<'PYEOF'
import sys
from datetime import datetime, timezone

logfile, cutoff_str, outfile = sys.argv[1], sys.argv[2], sys.argv[3]
cutoff_epoch = int(cutoff_str)
kept, pruned = [], 0

try:
    with open(logfile) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                kept.append(line)
                continue
            try:
                ts_str = stripped.split(' | ')[0].rstrip('Z')
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                if int(ts.timestamp()) >= cutoff_epoch:
                    kept.append(line)
                else:
                    pruned += 1
            except (ValueError, IndexError):
                kept.append(line)
except FileNotFoundError:
    pass

with open(outfile, 'w') as f:
    f.writelines(kept)

print(f"Log rotated: kept {len(kept)} lines, pruned {pruned} entries.", file=sys.stderr)
PYEOF

    mv "$tmp" "$LOG"
    echo "$now_epoch" > "$ROTATE_MARKER"
}

# ── commands ──────────────────────────────────────────────────────────────────

cmd_claim() {
    local resource="${1:?resource required}" agent="${2:?agent-id required}"
    local lock_dir="${LOCKS_DIR}/$(resource_to_dir "$resource")"

    if mkdir "$lock_dir" 2>/dev/null; then
        printf 'AGENT=%s\nRESOURCE=%s\nTIMESTAMP=%s\nEPOCH=%s\nPID=%s\n' \
            "$agent" "$resource" "$(ts)" "$(epoch)" "$$" > "${lock_dir}/owner"
        log_action CLAIM "$resource" "$agent"
        write_status
        rotate_log
        echo "✓ Claimed: ${resource} → ${agent}"
        return 0
    fi

    local owner_file="${lock_dir}/owner"
    if [ ! -f "$owner_file" ]; then
        echo "✗ ${resource} is locked (no owner file — partial write? retry shortly)" >&2
        return 1
    fi

    local lock_epoch lock_agent
    lock_epoch=$(grep '^EPOCH=' "$owner_file" | cut -d= -f2)
    lock_agent=$(grep '^AGENT=' "$owner_file" | cut -d= -f2)
    local age_secs=$(( $(epoch) - lock_epoch ))
    local stale_secs=$(( STALE_MINUTES * 60 ))

    if [ "$age_secs" -ge "$stale_secs" ]; then
        printf 'AGENT=%s\nRESOURCE=%s\nTIMESTAMP=%s\nEPOCH=%s\nPID=%s\n' \
            "$agent" "$resource" "$(ts)" "$(epoch)" "$$" > "${lock_dir}/owner"
        log_action STALE-CLAIM "$resource" "${agent} (evicted ${lock_agent}, age ${age_secs}s)"
        write_status
        echo "⚠ Claimed (stale lock from ${lock_agent} evicted, age ${age_secs}s): ${resource}"
        return 0
    fi

    echo "✗ ${resource} is held by ${lock_agent} (${age_secs}s ago). Choose a different task." >&2
    return 1
}

cmd_release() {
    local resource="${1:?resource required}" agent="${2:?agent-id required}"
    local lock_dir="${LOCKS_DIR}/$(resource_to_dir "$resource")"

    if [ ! -d "$lock_dir" ]; then
        echo "✗ No lock found for: ${resource}" >&2
        return 1
    fi

    if [ -f "${lock_dir}/owner" ]; then
        local lock_agent
        lock_agent=$(grep '^AGENT=' "${lock_dir}/owner" | cut -d= -f2)
        if [ "$lock_agent" != "$agent" ]; then
            echo "✗ Cannot release: ${resource} is held by ${lock_agent}, not ${agent}" >&2
            return 1
        fi
    fi

    rm -rf "$lock_dir"
    log_action RELEASE "$resource" "$agent"
    write_status
    rotate_log
    echo "✓ Released: ${resource}"
}

cmd_check() {
    local resource="${1:?resource required}"
    local lock_dir="${LOCKS_DIR}/$(resource_to_dir "$resource")"

    if [ ! -d "$lock_dir" ]; then
        echo "free"
        return 0
    fi

    if [ -f "${lock_dir}/owner" ]; then
        local age_secs lock_epoch
        lock_epoch=$(grep '^EPOCH=' "${lock_dir}/owner" | cut -d= -f2)
        age_secs=$(( $(epoch) - lock_epoch ))
        cat "${lock_dir}/owner"
        echo "AGE_SECONDS=${age_secs}"
        [ "$age_secs" -ge $(( STALE_MINUTES * 60 )) ] && echo "STATUS=STALE"
    else
        echo "locked (no owner metadata)"
    fi
}

cmd_status() {
    write_status
    cat "$STATUS_FILE"
    echo ""
    echo "=== Recent activity (last 10 lines) ==="
    tail -10 "$LOG" 2>/dev/null | grep -v '^#' | grep -v '^$' || true
}

cmd_cleanup() {
    local now_epoch stale_secs removed=0
    now_epoch=$(epoch)
    stale_secs=$(( STALE_MINUTES * 60 ))

    for lock_dir in "${LOCKS_DIR}"/*/; do
        [ -d "$lock_dir" ] || continue
        [ -f "${lock_dir}/owner" ] || continue
        local lock_epoch lock_agent resource age_secs
        lock_epoch=$(grep '^EPOCH=' "${lock_dir}/owner" | cut -d= -f2)
        lock_agent=$(grep '^AGENT=' "${lock_dir}/owner" | cut -d= -f2)
        resource=$(grep  '^RESOURCE=' "${lock_dir}/owner" | cut -d= -f2)
        age_secs=$(( now_epoch - lock_epoch ))
        if [ "$age_secs" -ge "$stale_secs" ]; then
            rm -rf "$lock_dir"
            log_action CLEANUP "$resource" "cleanup (evicted ${lock_agent}, age ${age_secs}s)"
            echo "Removed stale lock: ${resource} (${lock_agent}, ${age_secs}s old)"
            removed=$(( removed + 1 ))
        fi
    done

    write_status
    rotate_log
    echo "Done. Removed ${removed} stale lock(s)."
}

# ── dispatch ──────────────────────────────────────────────────────────────────
case "${1:-status}" in
    claim)   cmd_claim   "${2:-}" "${3:-}" ;;
    release) cmd_release "${2:-}" "${3:-}" ;;
    check)   cmd_check   "${2:-}" ;;
    status)  cmd_status ;;
    cleanup) cmd_cleanup ;;
    rotate)  rotate_log && echo "Log rotation check complete." ;;
    *)
        echo "Usage: $0 {claim|release|check|status|cleanup|rotate} [resource] [agent-id]" >&2
        exit 1
        ;;
esac
