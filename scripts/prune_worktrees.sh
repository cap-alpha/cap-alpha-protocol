#!/usr/bin/env bash
# Prune stale agent worktrees. Run weekly (or before /go).
#
# - `git worktree prune` removes registry entries whose dir is gone.
# - We additionally remove worktrees whose branch is already merged into main
#   AND whose dir has been untouched for >7 days.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

git worktree prune -v

CUTOFF=$(($(date +%s) - 7*86400))
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
  [ "$mtime" -gt "$CUTOFF" ] && continue

  if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
    echo "removing merged stale worktree: $wt (branch=$branch)"
    git worktree remove --force "$wt" || true
    git branch -D "$branch" 2>/dev/null || true
  fi
done

git worktree prune -v
echo "done. active worktrees:"
git worktree list
