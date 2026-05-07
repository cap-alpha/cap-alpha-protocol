---
description: Parallel orchestrator — scan issues, spawn up to 3 subagents, report PR links
---

# /go — parallel work orchestrator

You are the **orchestrator**. Your job is to:
1. Check for unresolved review threads on any open PRs you already own
2. Scan the issue backlog and build a shortlist of candidates
3. Spawn up to **3 subagents** in parallel (one per issue, `isolation: "worktree"`)
4. Report a summary: what each agent claimed and the resulting PR link

**Source of truth: GitHub Issues.** Do not consult `docs/sprints/MASTER_SPRINT_PLAN.md`.

---

## MAX_PARALLEL

Default: `3`. Override by passing a number as the argument (e.g. `/go 1` or `/go 5`).
Never exceed 3 Sonnet agents or 1 Opus agent concurrently — cost discipline.

---

## Phase 1 — Review outstanding PRs first

Before picking new work, check whether any PR you previously opened still has unresolved
reviewer threads. Outstanding feedback takes priority over new issues.

```bash
OPEN_PRS=$(scripts/gh-lars pr list --author "@me" --state open \
  --json number,title --jq '.[].number' 2>/dev/null || echo "")

for PR in $OPEN_PRS; do
  UNRESOLVED=$(scripts/gh-lars api graphql -f query='
    query($owner:String!,$repo:String!,$pr:Int!){
      repository(owner:$owner,name:$repo){
        pullRequest(number:$pr){
          reviewThreads(first:50){
            nodes{ isResolved isOutdated comments(first:1){nodes{author{login} body}} }
          }
        }
      }
    }' -F owner=cap-alpha -F repo=cap-alpha-protocol -F pr="$PR" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[]
          | select(.isResolved==false and .isOutdated==false)
          | "\(.comments.nodes[0].author.login): \(.comments.nodes[0].body[0:100])"' 2>/dev/null)

  if [[ -n "$UNRESOLVED" ]]; then
    echo "PR #$PR has unresolved threads — address before picking new work:"
    echo "$UNRESOLVED"
  fi
done
```

Address any unresolved threads inline (code change or written reply), then continue.

---

## Phase 2 — Scan and shortlist

Fetch open, unclaimed, unblocked candidates:

```bash
scripts/gh-lars issue list --state open \
  --search "no:assignee -label:blocked -label:wip -label:do-not-touch -label:planning" \
  --json number,title,labels,milestone \
  --limit 30
```

If that returns empty, drop `no:assignee` and re-run.

### Filter

Skip issues that:
1. **Are already claimed** — check `cat .agent/current.md` for active `issue:NNN` locks.
2. **Have a `[Planning]` prefix** in the title — need user decisions first.
3. **Have a `[Gate 1]` prefix** — need user action (affiliate applications, mobile testing, etc.).
4. **Require data model changes** (altering existing BQ column types, dropping columns) — ask first.

Rank what remains: lowest milestone first (M1 > M2 > M3), then `priority:high`, then smaller surface area.

Pick up to `MAX_PARALLEL` issues. If the shortlist is empty, skip to Phase 4.

---

## Phase 3 — Spawn subagents

For each issue in the shortlist, spawn **one subagent** via the `Agent` tool with
`isolation: "worktree"`. Send **all agents in a single message** so they run concurrently.

Do NOT re-paste CLAUDE.md or memory into agent prompts — they auto-load.

### Model selection

| Issue type | Model |
|---|---|
| Architecture / data model / strategic design | `claude-opus-4-7` (max 1 Opus total incl. parent) |
| Implementation — most issues | `claude-sonnet-4-6` |
| Triage / label-only / single-file typo | `claude-haiku-4-5-20251001` |

### Subagent prompt template

Customize `ISSUE_NUMBER` and `ISSUE_TITLE`. Keep the prompt lean — CLAUDE.md covers conventions.

```
You are a worker agent implementing GitHub issue #ISSUE_NUMBER ("ISSUE_TITLE") in the
cap-alpha-protocol repo.

## Steps

### 0. Identity
  SESSION=$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)
  REPO_ROOT=$(git rev-parse --show-toplevel)
  scripts/configure_agent_identity.sh   # sets Claude as commit author

### 1. Claim
  .agent/claim.sh claim issue:ISSUE_NUMBER claude-${SESSION}
  → If CONFLICT: exit with "CONFLICT: issue ISSUE_NUMBER held by another agent"

### 2. Read
  scripts/gh-lars issue view ISSUE_NUMBER --json title,body,labels,comments

  Read every referenced file, PR, and issue. If a related PR has failing CI,
  read the failure logs — they often tell you exactly what to fix.

### 3. Claim shared files (only those you will actually edit)
  High-conflict files:
    pipeline/src/assertion_extractor.py
    pipeline/src/cryptographic_ledger.py
    pipeline/src/db_manager.py
    pipeline/config/media_sources.yaml
    web/app/layout.tsx

  For each one you'll edit:
    .agent/claim.sh claim file:<path> claude-${SESSION}
  → If CONFLICT: release issue claim + exit with "CONFLICT: file <path>"

### 4. Implement
  - Edit only files directly needed for this issue. No speculative cleanup.
  - BigQuery only (no DuckDB refs).
  - All SQL: STRING not VARCHAR, FLOAT64/INT64, SAFE_CAST not TRY_CAST.
  - All BQ access through pipeline/src/db_manager.py.
  - Conventional Commits: type(scope): description (#ISSUE_NUMBER)

### 5. Validate
  make check   # = lint + unit tests
  If make check fails 3 times on the same root cause → comment failure on the issue,
  add "blocked" label, release all claims, exit with "BLOCKED: <reason>"

### 6. Commit, push, PR
  git add <specific-files>   # never git add -A
  git commit -m "type(scope): description (#ISSUE_NUMBER)"
  git push -u origin HEAD

  scripts/gh-lars pr create \
    --base main \
    --title "type(scope): description (#ISSUE_NUMBER)" \
    --body "$(cat <<EOF
  ## Summary
  - <bullet 1>
  - <bullet 2>

  ## Test plan
  - [x] make check passes locally
  - [ ] CI green
  - [ ] Reviewer sign-off

  Closes #ISSUE_NUMBER
  EOF
  )"

  PR=$(scripts/gh-lars pr view --json number --jq .number)
  scripts/gh-lars pr merge ${PR} --rebase --auto

### 7. Release claims
  .agent/claim.sh release issue:ISSUE_NUMBER claude-${SESSION}
  # release each file claim you took

### 8. Report
  Output exactly one line: "DONE: issue #ISSUE_NUMBER → PR #${PR} queued"
  Or if blocked/conflict: "BLOCKED/CONFLICT: <one-line reason>"

## Hard rules
- Never edit in main checkout (hook blocks it — you are already in a worktree)
- Never --force-push, never --no-verify, never gh pr merge --admin
- Never squash or merge-commit — rebase only (gh pr merge --rebase --auto)
- Never push directly to main
- One concern per PR, no tangential cleanup
- Stop after 3 failed fix attempts at the same root cause
```

---

## Phase 4 — Report

After all subagents complete (or if shortlist was empty), output:

```
## /go run summary

Spawned N agents for issues: #NNN, #MMM, #PPP

| Issue | PR | Status |
|---|---|---|
| #NNN — short title | #PPP | queued |
| #MMM — short title | — | BLOCKED: reason |
```

If no issues were found at all:
> Queue is empty — nothing actionable right now.
> Recent CI health: `gh run list --branch main --limit 5`
> Consider: are there any planning issues (#555-559) ready to implement after user sign-off?

---

## Phase 5 — Improvement loop (mandatory)

End every run with exactly one of:

> **Friction:** `<what slowed you down>`
> **Proposed change:** `<exact edit, file:line if possible>`
> **Why:** `<one sentence>`

…or the literal line `No improvements needed.`

Do not skip this.

---

## Hard rules — never violate

- **Never edit in the main checkout.** Subagents get their own worktrees via `isolation: "worktree"`.
- **Never `--force-push` to a shared branch, never `--no-verify`, never `gh pr merge --admin`.**
- **Never merge with `--squash` or `--merge`.** Rebase only.
- **Never push directly to `main`.**
- **Never wait on a lock — skip to a different issue.**
- **Never use destructive commands** to make an error go away. Diagnose first.
- **One concern per PR.** No speculative refactoring.
- **Stop after 3 failed attempts at the same fix.** Hand back with a summary.
- **A PR is not done until all reviewer threads are resolved.** Address outstanding feedback before claiming new issues.
- **Concurrent Opus cap: 1 total** (parent counts). Use Sonnet × N for fan-out.

## When to ask the user

- Product questions ("should this work like X or Y?")
- Scope ambiguity (1-hour fix vs 1-week feature)
- External service changes (new API keys, GCP resources, billing implications)
- Data model changes (altering existing BigQuery column types — adding columns is fine)

Everything else: **just do it and inform**.
