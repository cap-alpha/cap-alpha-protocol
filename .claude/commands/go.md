---
description: Pick the next open issue, do the work, open a PR, queue it for landing
---

# /go — kick off regular work

You are an autonomous engineer working through the GitHub issue backlog.

**Source of truth: GitHub Issues.** The old `docs/sprints/MASTER_SPRINT_PLAN.md` flow is deprecated — do not consult it.

Run the loop below until the queue is empty or you hit a hard blocker. **Always work in a git worktree. Always rebase. Never squash. Never push to `main`. Never bypass hooks or branch protection.**

If at any point you are unsure what to do, **prefer the cautious path**: stop, document what you saw, and ask. A correct half-step is better than a confident wrong step.

---

## 0. Set up your session identity

You need a stable, unique-ish session ID for the lock system and PR comments. Compute it once at the start of the run:

```bash
SESSION=$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)
echo "Session: $SESSION"
```

Result looks like `7f3ab9c1`. Use `claude-${SESSION}` (e.g. `claude-7f3ab9c1`) wherever this doc says `claude-<session>`.

You also need the repo root and your GitHub login:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
GH_USER=$(gh api user --jq .login)
```

Once you're inside a worktree (step 2), set the agent git identity for that worktree so commits aren't attributed to the human user:

```bash
scripts/configure_agent_identity.sh
```

This sets `user.name="Claude Code (agent)"` and `user.email="noreply@anthropic.com"` locally for the worktree. Idempotent.

---

## 1. Pick the next issue

```bash
gh issue list --state open \
  --search "no:assignee -label:blocked -label:wip -label:do-not-touch" \
  --json number,title,labels,milestone \
  --limit 30
```

If that returns an empty array, drop the `no:assignee` filter — issues self-assigned by humans are still pickable as long as nothing else excludes them:

```bash
gh issue list --state open \
  --search "-label:blocked -label:wip -label:do-not-touch" \
  --json number,title,labels,milestone,assignees \
  --limit 30
```

Then filter:

1. **Skip already-claimed issues.** Read `cat ${REPO_ROOT}/.agent/current.md`. The file lists active claims as lines like:
   ```
   - issue:194  by claude-7f3ab9c1  at 2026-04-26T19:04:00Z
   - file:pipeline/src/db_manager.py  by claude-7f3ab9c1  at 2026-04-26T19:04:00Z
   ```
   If your candidate issue number appears, skip it.

2. **Prefer the lowest open milestone.** In this repo: M1 (Data) > M2 (API) > M3 (UI). If milestones aren't labeled, ignore this rule and use #3.

3. **Among ties, prefer:**
   - `priority:high` label
   - Smaller surface area (issue body mentions fewer files / one module)
   - Issues that **don't** touch the high-conflict shared files (see step 2 below)

4. **If nothing eligible exists**, stop. Skip to step 6 (improvement loop).

Pick exactly **one** issue. Set:

```bash
ISSUE=<number>            # e.g. ISSUE=194
TITLE_SLUG=<short-kebab>  # e.g. TITLE_SLUG=draft-pick-fallback   (3-5 words, lowercase, hyphens)
```

`TITLE_SLUG` is *your* short summary of the work, not the full issue title. Keep it under 30 chars.

---

## 2. Claim and isolate

Create a worktree on a new feature branch. **Never edit files in the main checkout** — there is a `PreToolUse` hook (`.claude/hooks/require-worktree.sh`) that will block your `Edit`/`Write` calls if you forget.

```bash
cd "$REPO_ROOT"
git fetch origin main
WORKTREE_DIR=".claude/worktrees/issue-${ISSUE}-${TITLE_SLUG}"
BRANCH="feat/${ISSUE}-${TITLE_SLUG}"

git worktree add "$WORKTREE_DIR" -b "$BRANCH" origin/main
cd "$WORKTREE_DIR"
scripts/configure_agent_identity.sh   # set Claude as commit author for this worktree
```

If `git worktree add` fails because the path or branch already exists, **do not delete or force**. Pick a different `TITLE_SLUG` (e.g. add `-v2`) and try again.

### Claim the issue

```bash
.agent/claim.sh claim issue:${ISSUE} claude-${SESSION}
```

Possible outcomes:

- **Success** (`OK: claimed issue:${ISSUE} ...`) → proceed.
- **Conflict** (`CONFLICT: held by claude-XXXXXXXX ...`) → release any claims you've already taken in this run, remove your worktree (`cd .. && git worktree remove "$WORKTREE_DIR"` then `git branch -D "$BRANCH"`), and **go back to step 1 to pick a different issue**.
- **Refuses to run** (`refuse to run from main checkout`) → you forgot to `cd` into the worktree. Fix and retry.

### Claim shared files (only those you'll actually edit)

The high-conflict files (per CLAUDE.md) are:

```
pipeline/src/assertion_extractor.py
pipeline/src/cryptographic_ledger.py
pipeline/src/db_manager.py
pipeline/config/media_sources.yaml
web/app/layout.tsx
```

**For each one you will edit in this PR**, run:

```bash
.agent/claim.sh claim file:<path> claude-${SESSION}
```

If any file claim conflicts, release everything you've claimed and pick a different issue:

```bash
.agent/claim.sh release issue:${ISSUE} claude-${SESSION}
# (release any file claims that succeeded)
cd .. && git worktree remove "$WORKTREE_DIR" && git branch -D "$BRANCH"
```

### Comment on the issue

```bash
gh issue comment "$ISSUE" --body "🤖 working on this on branch \`${BRANCH}\` — Claude (/go), session ${SESSION}"
```

---

## 3. Execute

### Read context first
```bash
gh issue view "$ISSUE" --json title,body,labels,milestone,comments
```

If the issue references other issues, PRs, or files, open them too. If a related PR has failing CI, read the failure logs — they often tell you what to fix.

### Plan if non-obvious
If the design isn't immediately clear, write `implementation_plan.md` in the worktree first (250 words max), then implement against it. Don't let planning balloon — you can always revise.

### Implement
- BigQuery only (no DuckDB / MotherDuck refs).
- Medallion layers: bronze → silver → gold.
- All BQ access through `pipeline/src/db_manager.py`.
- All SQL must be valid BigQuery (`STRING` not `VARCHAR`, `FLOAT64`/`INT64`, `SAFE_CAST` not `TRY_CAST`, `MOD()` not `%`).
- Conventional Commits (see step 4 for the exact format).

### Validate locally — `make check` is the gate
```bash
make check     # = make lint + make test
```

If `make` itself isn't found or `make check` fails because deps aren't installed:

```bash
make setup     # creates .venv and installs hooks (one-time)
make check
```

**Never push red.** If `make check` fails:
1. Read the actual failure output.
2. Fix it. (Lint fixes: `make lint-fix`.)
3. Re-run `make check`.
4. If it fails 3 times in a row on the same root cause → **stop spinning**. Comment the failure summary on the issue, add `label:blocked`, release locks (step 5), do NOT push, and pick the next issue.

E2E tests (`make test-e2e`) and the Spotrac scraper (`make pipeline-scrape`) require Docker. Skip those unless the issue specifically asks for them.

---

## 4. Open the PR and queue it

```bash
git status -s          # confirm what changed
git add <specific-files>   # NEVER `git add -A` or `git add .`
git status -s          # confirm staging
git commit -m "type(scope): summary (#${ISSUE})"
```

### Conventional Commits cheat sheet

| type | when | example |
|---|---|---|
| `feat` | new user-visible behavior | `feat(api): add /v1/cap/contracts endpoint (#108)` |
| `fix` | bug fix | `fix(extract): handle missing draft_year (#274)` |
| `chore` | tooling, deps, no behavior change | `chore(ci): bump pytest to 8.2 (#290)` |
| `refactor` | structural change, no behavior change | `refactor(db): extract Spotrac client (#221)` |
| `test` | tests only | `test(resolve): unit tests for draft pick parsing (#259)` |
| `docs` | docs only | `docs(readme): document /go workflow` |
| `ci` | CI/workflow files only | `ci(github): require linear history on main` |

Scope is the module (`api`, `extract`, `web`, `db`, `ci`, etc.). Keep the title under 72 chars.

If pre-commit hooks modify files, **stage them and amend** — don't `--no-verify`:

```bash
git add -u
git commit --amend --no-edit
```

### Push and open the PR

```bash
git push -u origin HEAD

gh pr create \
  --base main \
  --title "type(scope): summary (#${ISSUE})" \
  --body "$(cat <<EOF
## Summary
- <bullet 1>
- <bullet 2>

## Test plan
- [x] make check passes locally
- [ ] CI green
- [ ] Reviewer sign-off

Closes #${ISSUE}
EOF
)"
```

Capture the PR number from the URL `gh pr create` prints (or `gh pr view --json number --jq .number`).

### Queue for auto-merge

```bash
PR=<the-number>
gh pr merge "$PR" --rebase --auto
```

**Always `--rebase`. Never `--squash` or `--merge`.** Repo settings now disallow squash/merge-commit and `main` requires linear history, but be explicit.

The PR will sit in the auto-merge queue waiting on:
1. Required CI checks: `Lint Code`, `Run Data Quality Tests (3.11)`, `test (3.10)`, `preflight-build`.
2. One human approval, **or** the auto-approve workflow firing once Copilot reviews and no reviewer requested changes.

### If auto-merge isn't accepted
`gh pr merge --auto` can refuse if the repo's auto-merge isn't enabled or your token lacks permission. Comment on the PR with what you tried and continue. Don't try to bypass it.

---

## 5. Release locks (but you're not "done" yet)

```bash
.agent/claim.sh release issue:${ISSUE} claude-${SESSION}
# Release every file claim you took:
.agent/claim.sh release file:<path> claude-${SESSION}
```

You do **not** need to wait for the PR to land before releasing locks — auto-merge handles landing asynchronously, and other agents shouldn't be blocked from your shared-file claims. **But your work on this issue isn't "done" yet.**

### Definition of done — a PR is NOT done until:

1. **All review comments are addressed.** This includes:
   - Inline review comments (from humans or Copilot or `claude-review`).
   - Top-level PR review comments.
   - PR review threads with `state != "RESOLVED"`.
   - Issue/PR comments that ask for a change (anything not just informational).
2. **All review threads are resolved** (either by you marking them resolved after addressing, or by the reviewer).
3. **Either the PR is merged, OR every reviewer who requested changes has been responded to with a code change or a clear written reply.**

You — the agent who opened the PR — are responsible for addressing the comments on that PR. Sub-agents you spawn inherit this responsibility for any PR they open. Do **not** call your work complete and do **not** report back to the user as "done" while comments are outstanding.

### Before picking the next issue in step 1, ALWAYS check your own open PRs:

```bash
# List PRs you opened that are still open
gh pr list --author "@me" --state open --json number,title,reviewDecision,url \
  --jq '.[] | "PR #\(.number) [\(.reviewDecision // "PENDING")]: \(.title)"'

# For each, look at unresolved review threads + unaddressed comments
for PR in $(gh pr list --author "@me" --state open --json number --jq '.[].number'); do
  echo "=== PR #$PR ==="
  # Unresolved review threads (GraphQL, since REST doesn't expose isResolved)
  gh api graphql -f query='
    query($owner:String!,$repo:String!,$pr:Int!){
      repository(owner:$owner,name:$repo){
        pullRequest(number:$pr){
          reviewThreads(first:50){
            nodes{ isResolved isOutdated comments(first:1){nodes{author{login} body}} }
          }
        }
      }
    }' -F owner=cap-alpha -F repo=cap-alpha-protocol -F pr="$PR" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false and .isOutdated==false) | "  UNRESOLVED: \(.comments.nodes[0].author.login): \(.comments.nodes[0].body[0:120])"'
  # Reviews that requested changes
  gh pr view "$PR" --json reviews \
    --jq '.reviews[] | select(.state=="CHANGES_REQUESTED") | "  CHANGES_REQUESTED by \(.author.login): \(.body[0:120])"'
done
```

**If any PR you opened has unresolved threads or unaddressed `CHANGES_REQUESTED` reviews, fix those FIRST**, before picking up a new issue. Workflow:

1. `cd` into the worktree for that PR's branch (or recreate it if pruned).
2. Re-claim the issue and any shared files you'll edit.
3. Address each comment with a code change OR a written reply that explains why no change is needed (if you disagree, say so politely with reasoning).
4. After pushing the fix, **resolve the thread**:
   ```bash
   # Get thread IDs and resolve each addressed one:
   gh api graphql -f query='
     query($owner:String!,$repo:String!,$pr:Int!){
       repository(owner:$owner,name:$repo){
         pullRequest(number:$pr){
           reviewThreads(first:50){ nodes{ id isResolved isOutdated } }
         }
       }
     }' -F owner=cap-alpha -F repo=cap-alpha-protocol -F pr="$PR"

   gh api graphql -f query='
     mutation($id:ID!){
       resolveReviewThread(input:{threadId:$id}){ thread{ isResolved } }
     }' -F id="<thread-id>"
   ```
5. Once all threads are resolved and CI is green, return to picking up a new issue.

Per saved feedback (`feedback_pr_landing_protocol`): resolve threads via GraphQL before approving / re-approving.

---

## 6. End-of-run improvement loop (mandatory)

When the queue is empty, you hit a hard blocker, or the user asks you to stop, end your final response with **one** of these:

### Option A — improvement suggestions

Concrete proposed edits to this `/go` command, the agent harness (`.claude/`), or repo automation, based on friction observed during the run. Cite specific commands, files, or PR numbers. Format:

> **Friction:** `<what slowed you down>`
> **Proposed change:** `<exact edit, file:line if possible>`
> **Why:** `<one sentence>`

### Option B — `No improvements needed.`

Only if the run was genuinely clean.

This is mandatory per saved feedback. Do not skip.

---

## Hard rules — never violate

- **Never edit in the main checkout.** Always in a worktree under `.claude/worktrees/`.
- **Never `git push --force` or `--force-with-lease` to a shared branch, never `--no-verify`, never `gh pr merge --admin`.**
- **Never `git rebase -i` or `git commit --amend` on a pushed-and-shared branch** — only on your fresh feature branch before opening the PR.
- **Never merge with `--squash` or `--merge`.** Rebase only.
- **Never push directly to `main`.**
- **Never wait on a lock — pick a different issue.**
- **Never use destructive commands** (`rm -rf`, `git reset --hard`, `git checkout .`) to "make the error go away." Diagnose first.
- **One concern per PR.** No speculative refactoring or tangential cleanups.
- **Stop after 3 failed attempts at the same fix.** Hand back with a summary.
- **A PR is not "done" until all review comments are addressed and threads resolved.** Outstanding feedback on a PR you (or a sub-agent you spawned) opened takes priority over picking up a new issue.

## When to ask the user (instead of deciding)

Per `CLAUDE.md`:
- Product questions ("should this work like X or Y?")
- Scope ambiguity (1-hour fix vs 1-week feature)
- External service changes (new API keys, GCP resources, billing)
- Data model changes (altering existing BigQuery schemas — adding columns is fine)

Everything else: **just do it and inform**.

---

## Worked example

You picked issue #274: "extract draft_year field for draft pick predictions."

```bash
SESSION=$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)
# Session: a1b2c3d4
REPO_ROOT=$(git rev-parse --show-toplevel)
ISSUE=274
TITLE_SLUG=draft-year-fallback

cd "$REPO_ROOT"
git fetch origin main
git worktree add ".claude/worktrees/issue-${ISSUE}-${TITLE_SLUG}" -b "feat/${ISSUE}-${TITLE_SLUG}" origin/main
cd ".claude/worktrees/issue-${ISSUE}-${TITLE_SLUG}"

.agent/claim.sh claim issue:${ISSUE} claude-${SESSION}
.agent/claim.sh claim file:pipeline/src/assertion_extractor.py claude-${SESSION}

gh issue comment ${ISSUE} --body "🤖 working on this on branch \`feat/${ISSUE}-${TITLE_SLUG}\` — Claude (/go), session ${SESSION}"
gh issue view ${ISSUE} --json title,body,labels

# ... read code, make targeted edits to assertion_extractor.py + tests ...

make check
# ... fix any issues, repeat until green ...

git add pipeline/src/assertion_extractor.py pipeline/tests/test_assertion_extractor.py
git commit -m "fix(extract): extract draft_year field for draft pick predictions (#${ISSUE})"
git push -u origin HEAD

gh pr create --base main \
  --title "fix(extract): extract draft_year field for draft pick predictions (#${ISSUE})" \
  --body "$(cat <<EOF
## Summary
- Adds draft_year regex extraction in assertion_extractor.py
- Falls back to current year minus draft offset when missing

## Test plan
- [x] make check passes locally
- [ ] CI green
- [ ] Reviewer sign-off

Closes #${ISSUE}
EOF
)"

PR=$(gh pr view --json number --jq .number)
gh pr merge ${PR} --rebase --auto

.agent/claim.sh release issue:${ISSUE} claude-${SESSION}
.agent/claim.sh release file:pipeline/src/assertion_extractor.py claude-${SESSION}

# back to step 1
```
