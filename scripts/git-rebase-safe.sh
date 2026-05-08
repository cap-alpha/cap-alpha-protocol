#!/usr/bin/env bash
# git-rebase-safe.sh — fetch PR branch before rebasing to avoid orphaning third-party commits.
#
# Usage: scripts/git-rebase-safe.sh <worktree-path> <branch>
#
# Problem (observed 2026-05-07): when an agent rebases a PR branch onto
# origin/main, it only fetches main — not the PR branch itself. If a third
# party (e.g. copilot-swe-agent) has pushed commits to the branch between our
# last local fetch and the force-push, those commits are silently orphaned and
# lost.
#
# PR #704: commit b27cd08 (three real fixes by copilot-swe-agent) was dropped
# this way and only recovered manually. Same pattern on #725 (7c3e697) and
# #729 (3e10cf7).
#
# Fix sequence:
#   1. git fetch origin <branch>          — bring remote tip into FETCH_HEAD
#   2. find orphaned commits on origin/<branch> not in local HEAD
#   3. cherry-pick any orphans before rebasing
#   4. git rebase origin/main
#   5. git push --force-with-lease origin <branch>
#
# Example orphan scenario:
#   Local HEAD:          A - B - C  (our commits)
#   origin/<branch>:     A - B - C - D  (D pushed by copilot after our last fetch)
#   Without this script: rebase drops D; push orphans it.
#   With this script:    D is detected, cherry-picked, then rebase includes it.

set -euo pipefail

usage() {
    echo "Usage: $0 <worktree-path> <branch>" >&2
    echo "" >&2
    echo "  <worktree-path>  Absolute path to the git worktree (use git rev-parse to verify)" >&2
    echo "  <branch>         PR branch name (e.g. fix/746-fetch-before-rebase)" >&2
    echo "" >&2
    echo "The script fetches origin/<branch>, cherry-picks any orphaned commits pushed" >&2
    echo "by third parties since last fetch, then rebases onto origin/main and" >&2
    echo "force-pushes with lease." >&2
    exit 1
}

if [ $# -lt 2 ]; then
    usage
fi

WORKTREE_PATH="$1"
BRANCH="$2"

# Validate the worktree path
if [ ! -d "$WORKTREE_PATH" ]; then
    echo "ERROR: worktree path does not exist: $WORKTREE_PATH" >&2
    exit 1
fi

# All git operations run inside the worktree to avoid accidentally operating on
# the main checkout (which is blocked by require-worktree.sh pre-tool hook).
run_git() {
    git -C "$WORKTREE_PATH" "$@"
}

echo "==> git-rebase-safe: branch=$BRANCH worktree=$WORKTREE_PATH"

# Step 1: Fetch the PR branch itself (not just main)
echo "--> Step 1: Fetching origin/$BRANCH ..."
run_git fetch origin "$BRANCH"

# Step 2: Identify orphaned commits — commits on origin/<branch> not in our local HEAD
echo "--> Step 2: Checking for orphaned commits on origin/$BRANCH ..."
ORPHANS=$(run_git log --oneline "origin/$BRANCH" --not HEAD 2>/dev/null || true)

if [ -n "$ORPHANS" ]; then
    ORPHAN_COUNT=$(echo "$ORPHANS" | wc -l | tr -d ' ')
    echo "    WARNING: $ORPHAN_COUNT orphaned commit(s) found on origin/$BRANCH not in local HEAD:"
    echo "$ORPHANS" | sed 's/^/      /'
    echo ""

    # Step 3: Cherry-pick orphans in chronological order (oldest first)
    echo "--> Step 3: Cherry-picking $ORPHAN_COUNT orphaned commit(s) ..."
    ORPHAN_SHAS=$(run_git rev-list --reverse "origin/$BRANCH" --not HEAD)
    run_git cherry-pick $ORPHAN_SHAS
    echo "    Cherry-pick complete."
else
    echo "    No orphaned commits found — origin/$BRANCH is in sync with local HEAD."
fi

# Step 4: Fetch main and rebase
echo "--> Step 4: Fetching origin/main and rebasing ..."
run_git fetch origin main
run_git rebase origin/main

# Step 5: Force-push with lease (fails if someone pushed to the branch again
# between our fetch and push — safe by design)
echo "--> Step 5: Pushing $BRANCH to origin with --force-with-lease ..."
run_git push --force-with-lease origin "$BRANCH"

echo "==> git-rebase-safe: done. Branch $BRANCH is now rebased on origin/main."
