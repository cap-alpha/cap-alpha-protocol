#!/bin/bash
# PreToolUse hook — blocks file-editing tools when CWD is the main checkout,
# UNLESS the target file is inside a registered worktree.
#
# Enforces: agents must work in a git worktree, never directly in the main
# checkout. Prevents concurrent agents from stepping on each other's edits.
#
# Two-stage check:
#   1. If the tool's target file_path resolves inside any registered worktree,
#      allow it — subagents that can't call EnterWorktree (CWD isolation) still
#      need to write to their own worktree paths.
#   2. Fall back to CWD check: in a linked worktree git_dir != git_common_dir.
#
# Input: JSON on stdin from Claude Code hook harness:
#   { "tool_name": "Write", "tool_input": { "file_path": "...", ... } }
#
# Exit codes:
#   0 — allow the tool call
#   2 — block (stderr is shown to Claude so it can self-correct)

set -euo pipefail

# ── Stage 1: file-path check ────────────────────────────────────────────────
# Read tool input JSON from stdin; extract file_path if present.
tool_json="$(cat 2>/dev/null || true)"
file_path="$(printf '%s' "$tool_json" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', d)
    print(ti.get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null || true)"

if [ -n "$file_path" ]; then
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$repo_root" ]; then
        # Resolve to absolute path (file may not exist yet — use dirname).
        dir_part="$(dirname "$file_path")"
        base_part="$(basename "$file_path")"
        dir_abs="$(cd "$dir_part" 2>/dev/null && pwd || echo "$dir_part")"
        file_abs="$dir_abs/$base_part"

        # Allow if target is inside any registered worktree (skip main checkout).
        while IFS= read -r wt_path; do
            [ "$wt_path" = "$repo_root" ] && continue   # skip main
            [ -z "$wt_path" ] && continue
            if [[ "$file_abs" == "$wt_path"/* ]]; then
                exit 0
            fi
        done < <(git worktree list --porcelain 2>/dev/null \
                 | grep '^worktree ' | sed 's/^worktree //')
    fi
fi

# ── Stage 2: CWD-based check ────────────────────────────────────────────────
# In a linked worktree, git_dir resolves to <main>/.git/worktrees/<name>
# while git_common_dir always points to the main .git.  They differ ⟺ worktree.
git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
git_common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"

if [ -z "$git_dir" ] || [ -z "$git_common_dir" ]; then
    exit 0  # outside any git repo — allow
fi

git_dir_abs="$(cd "$git_dir" 2>/dev/null && pwd || echo "$git_dir")"
git_common_dir_abs="$(cd "$git_common_dir" 2>/dev/null && pwd || echo "$git_common_dir")"

if [ "$git_dir_abs" != "$git_common_dir_abs" ]; then
    exit 0  # we are inside a linked worktree — allow
fi

cat >&2 <<'MSG'
✗ BLOCKED: file edits are not allowed in the main repository checkout.

This project enforces git worktree isolation so concurrent agents cannot
step on each other's branches, staged changes, or working-tree edits.

To proceed:
  1. Use the EnterWorktree tool to create an isolated worktree, OR
  2. Run: git worktree add .claude/worktrees/<name> -b <new-branch>
     then work inside that path (all writes will be allowed there).

After moving into a worktree, retry the edit.

Land PRs via the merge queue: scripts/gh-lars pr merge <n> --rebase --auto
MSG
exit 2
