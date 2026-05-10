#!/usr/bin/env bash
# Prune stale agent worktrees. Called by the SessionStart hook (automatic) and
# by `make prune-worktrees` (manual).
#
# Strategy (in priority order):
#   MERGED   — branch is an ancestor of origin/main → remove immediately
#   CLOSED   — branch has a closed/abandoned PR → remove immediately
#   DETACHED — worktree is in detached-HEAD state → remove immediately
#   NO-PR    — branch has no open PR and dir is >7 days old → remove
#   OPEN-PR  — branch has an open PR → keep always
#
# Flags:
#   --dry-run   Print what would be removed without making any changes.
#
# Requirements: gh (via scripts/gh-lars), git, python3

set -euo pipefail

REPO_OWNER=$(gh repo view --json owner -q '.owner.login' 2>/dev/null || echo "cap-alpha")
REPO_NAME=$(gh repo view --json name -q '.name' 2>/dev/null || echo "cap-alpha-protocol")

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

GH="${REPO_ROOT}/scripts/gh-lars"
DRY_RUN=0
if [[ "${1-}" == "--dry-run" ]]; then
  DRY_RUN=1
  echo "[dry-run] no changes will be made"
fi

remove_worktree() {
  local wt="$1" branch="$2" reason="$3"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] would remove ($reason): $wt  branch=$branch"
    return
  fi
  echo "removing ($reason): $wt  branch=$branch"
  # Unlock locked worktrees so git worktree remove --force can proceed.
  local GIT_DIR
  GIT_DIR="$(git rev-parse --git-dir)"
  local lockfile="$GIT_DIR/worktrees/$(basename "$wt")/locked"
  [ -f "$lockfile" ] && rm -f "$lockfile"
  git worktree remove --force "$wt" 2>/dev/null || true
  git branch -D "$branch" 2>/dev/null || true
}

# ── Phase 1: fetch + fast local checks ───────────────────────────────────────
git fetch origin main --prune -q 2>/dev/null || true
git worktree prune -v

# Collect branches we need to check PR status for (skip merged/detached)
declare -a PENDING_BRANCHES=()
declare -A BRANCH_TO_WT=()
declare -A BRANCH_MTIME=()

CUTOFF=$(( $(date +%s) - 7 * 86400 ))

while IFS= read -r wt; do
  # Only manage worktrees under .claude/worktrees/
  case "$wt" in
    */.claude/worktrees/*) ;;
    *) continue ;;
  esac
  [ -d "$wt" ] || continue

  branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  [ -z "$branch" ] && continue

  # Detached HEAD
  if [ "$branch" = "HEAD" ]; then
    remove_worktree "$wt" "DETACHED" "detached-HEAD"
    continue
  fi

  # Merged into main — remove immediately, no age check
  if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
    remove_worktree "$wt" "$branch" "merged"
    continue
  fi

  # Queue for PR-status check
  PENDING_BRANCHES+=("$branch")
  BRANCH_TO_WT["$branch"]="$wt"
  mtime=$(stat -f %m "$wt" 2>/dev/null || stat -c %Y "$wt" 2>/dev/null || echo 0)
  BRANCH_MTIME["$branch"]="$mtime"

done < <(git worktree list --porcelain | awk '/^worktree / {print $2}')

# ── Phase 2: batch PR-state lookup via GraphQL ────────────────────────────────
# Build a lookup table: branch → PR state (OPEN | CLOSED | MERGED | NONE)
declare -A BRANCH_PR_STATE=()

if [[ ${#PENDING_BRANCHES[@]} -gt 0 ]]; then
  # Fetch up to 200 PRs in each state bucket (sufficient for this repo).
  PR_JSON=$("$GH" api graphql -f query='
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        open: pullRequests(states: [OPEN], first: 200) {
          nodes { headRefName state }
        }
        closed: pullRequests(states: [CLOSED, MERGED], first: 200) {
          nodes { headRefName state }
        }
      }
    }
  ' -f owner="$REPO_OWNER" -f repo="$REPO_NAME" 2>/dev/null || echo "")

  if [[ -n "$PR_JSON" ]]; then
    # Parse open PRs
    while IFS= read -r line; do
      [[ -n "$line" ]] && BRANCH_PR_STATE["$line"]="OPEN"
    done < <(echo "$PR_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
nodes = d.get('data',{}).get('repository',{}).get('open',{}).get('nodes',[])
for n in nodes: print(n['headRefName'])
" 2>/dev/null || true)

    # Parse closed/merged PRs (only record if not already marked OPEN)
    while IFS=$'\t' read -r br state; do
      [[ -n "$br" ]] && [[ -z "${BRANCH_PR_STATE[$br]-}" ]] && BRANCH_PR_STATE["$br"]="$state"
    done < <(echo "$PR_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
nodes = d.get('data',{}).get('repository',{}).get('closed',{}).get('nodes',[])
for n in nodes: print(n['headRefName'] + '\t' + n['state'])
" 2>/dev/null || true)
  fi
fi

# ── Phase 3: apply rules to pending branches ──────────────────────────────────
for branch in "${PENDING_BRANCHES[@]}"; do
  wt="${BRANCH_TO_WT[$branch]}"
  state="${BRANCH_PR_STATE[$branch]-NONE}"
  mtime="${BRANCH_MTIME[$branch]}"

  case "$state" in
    OPEN)
      echo "keeping (open PR): $wt  branch=$branch"
      ;;
    CLOSED|MERGED)
      remove_worktree "$wt" "$branch" "closed/merged PR"
      ;;
    NONE)
      if [[ "$mtime" -le "$CUTOFF" ]]; then
        remove_worktree "$wt" "$branch" "no PR + >7 days old"
      else
        echo "keeping (no PR, recent): $wt  branch=$branch"
      fi
      ;;
  esac
done

# ── Phase 4: final cleanup ────────────────────────────────────────────────────
git worktree prune -v
echo ""
echo "done. active worktrees: $(git worktree list | wc -l | tr -d ' ')"
if [[ $DRY_RUN -eq 0 ]]; then
  git worktree list
fi
