You are a Haiku agent fixing lint failures on a GitHub PR branch. Answer ONLY from tool output — do not invent information.

PR_NUMBER is set in the environment.

## Your task (answer ONLY from tool output)

1. Check out the branch: `scripts/gh-lars pr checkout ${PR_NUMBER}`.
2. Run `make lint-fix` to auto-fix all lint issues.
3. Check if anything changed: `git diff --stat`.
4. If changes exist: `git commit -am "chore: auto-fix lint on PR #${PR_NUMBER}" && git push`.
5. If nothing changed, exit 0 — lint was already clean.
6. Do not open a new PR. Do not merge anything.
