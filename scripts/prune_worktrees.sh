#!/usr/bin/env bash
# Prune stale agent worktrees. Called by the Claude Stop hook (automatic) and
# by `make prune-worktrees` (manual).
#
# Strategy:
#   1. git worktree prune — remove registry entries whose directory is gone.
#   2. For every .claude/worktrees/* entry whose branch is merged into main
#      AND whose directory is older than CUTOFF seconds:
#        a. Remove the git lock file so the force-remove can proceed.
#        b. git worktree remove --force
#        c. Delete the local branch ref.
set -euo pipefail

CUTOFF=${STALE_SECONDS:-$((2 * 86400))}  # default: 2 days

cd "$(git rev-parse --show-toplevel)"
GIT_DIR="$(git rev-parse --git-dir)"

git fetch origin main --prune -q 2>/dev/null || true
git worktree prune -v

git worktree list --porcelain | awk '/^worktree / {print $2}' | while read -r wt; do
  case "$wt" in
    *.claude/worktrees/*) ;;
    *) continue ;;
  esac
  [ -d "$wt" ] || continue

  branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  [ -z "$branch" ] && continue
  [ "$branch" = "HEAD" ] && continue

  mtime=$(stat -f %m "$wt" 2>/dev/null || stat -c %Y "$wt" 2>/dev/null || echo 0)
  [ "$mtime" -gt "$(($(date +%s) - CUTOFF))" ] && continue

  if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
    # Remove git's lock file so --force can actually delete a locked worktree.
    lockfile="$GIT_DIR/worktrees/$(basename "$wt")/locked"
    [ -f "$lockfile" ] && rm -f "$lockfile" && echo "unlocked: $wt"

    echo "removing merged stale worktree: $wt (branch=$branch)"
    git worktree remove --force "$wt" || true
    git branch -D "$branch" 2>/dev/null || true
  fi
done

git worktree prune -v
echo "done. active worktrees:"
git worktree list
