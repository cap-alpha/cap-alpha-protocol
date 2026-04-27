#!/usr/bin/env bash
# Configure git author identity for the current worktree so commits made by
# Claude agents are attributed to a Claude identity rather than the user's
# personal account. This is "Option C" from the identity discussion — the
# PR author on GitHub still reflects whoever owns the `gh` token, but the
# commit author on the diff (and in `git log`) shows as Claude.
#
# Usage:
#   scripts/configure_agent_identity.sh             # configure the worktree we're in
#   scripts/configure_agent_identity.sh --check     # just print, don't change
#
# Idempotent. Safe to call repeatedly. Refuses to run from the main checkout.
set -euo pipefail

CLAUDE_NAME="Claude Code (agent)"
CLAUDE_EMAIL="noreply@anthropic.com"

git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
git_common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [ -z "$git_dir" ] || [ -z "$git_common_dir" ]; then
  echo "not in a git repo — skipping" >&2
  exit 0
fi
git_dir_abs="$(cd "$git_dir" && pwd)"
git_common_dir_abs="$(cd "$git_common_dir" && pwd)"
if [ "$git_dir_abs" = "$git_common_dir_abs" ]; then
  echo "refusing to set agent identity in the main checkout" >&2
  echo "this script is intended for .claude/worktrees/* only" >&2
  exit 1
fi

current_name="$(git config --local --get user.name || echo '')"
current_email="$(git config --local --get user.email || echo '')"

if [ "${1-}" = "--check" ]; then
  echo "worktree:    $(git rev-parse --show-toplevel)"
  echo "user.name:   ${current_name:-<inherits global>}"
  echo "user.email:  ${current_email:-<inherits global>}"
  exit 0
fi

if [ "$current_name" = "$CLAUDE_NAME" ] && [ "$current_email" = "$CLAUDE_EMAIL" ]; then
  echo "agent identity already configured for this worktree"
  exit 0
fi

git config --local user.name  "$CLAUDE_NAME"
git config --local user.email "$CLAUDE_EMAIL"

echo "configured agent identity in $(git rev-parse --show-toplevel):"
echo "  user.name  = $CLAUDE_NAME"
echo "  user.email = $CLAUDE_EMAIL"
