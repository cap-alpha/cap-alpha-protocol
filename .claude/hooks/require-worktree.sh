#!/bin/bash
# PreToolUse hook — blocks file-editing tools when CWD is the main checkout.
#
# Enforces: agents must work in a git worktree (use the EnterWorktree tool),
# never directly in the main checkout. Prevents concurrent agents from
# stepping on each other's edits, branches, and staged changes.
#
# Detection: in a linked worktree, `git rev-parse --git-dir` resolves to
# something like `<main>/.git/worktrees/<name>`, while `git-common-dir`
# always points to the main `.git`. They differ ⇔ we are in a worktree.
#
# Exit codes:
#   0 — allow the tool call
#   2 — block (stderr is shown to Claude so it can self-correct)

set -euo pipefail

# Resolve git directories. Outside a git repo, allow the tool.
git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
git_common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"

if [ -z "$git_dir" ] || [ -z "$git_common_dir" ]; then
    exit 0
fi

# Normalize to absolute paths so the comparison is reliable.
git_dir_abs="$(cd "$git_dir" 2>/dev/null && pwd || echo "$git_dir")"
git_common_dir_abs="$(cd "$git_common_dir" 2>/dev/null && pwd || echo "$git_common_dir")"

# In a linked worktree these differ; in the main checkout they're identical.
if [ "$git_dir_abs" != "$git_common_dir_abs" ]; then
    exit 0
fi

cat >&2 <<'MSG'
✗ BLOCKED: file edits are not allowed in the main repository checkout.

This project enforces git worktree isolation so concurrent agents cannot
step on each other's branches, staged changes, or working-tree edits.

To proceed:
  1. Use the EnterWorktree tool to create an isolated worktree, OR
  2. Run: git worktree add .claude/worktrees/<name> -b <new-branch>
     and then `cd` into it.

After moving into a worktree, retry the edit.

When the PR is ready, land it via the GitHub merge queue:
  gh pr merge <pr-number> --squash --auto
MSG
exit 2
