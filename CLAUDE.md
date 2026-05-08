# NFL Dead Money / Pundit Prediction Ledger — Agent Instructions

> ## ⚠️ STOP — READ THIS FIRST
>
> **All agent work on this repo MUST happen in a git worktree, and all PRs MUST land via the GitHub merge queue.**
>
> - **One concern per PR.** A PR may touch multiple files but must address a single logical change. Never bundle an unrelated fix into the same PR even if convenient. If you catch a bug while working on a feature, open a separate PR for the bug fix.
> - **Repository settings are OFF LIMITS.** Never modify branch protection rules, webhook config, Actions settings, collaborators, or any GitHub repository settings via `gh api` or any other mechanism. This includes `gh api repos/.../branches/.../protection`, `gh repo edit`, and similar. The GitHub App intentionally lacks Administration permission.
> - **Never edit files in the main checkout.** A PreToolUse hook (`.claude/hooks/require-worktree.sh`) blocks Edit/Write/MultiEdit when CWD is the main repo. If you see that error, switch to a worktree.
> - **Use `EnterWorktree` first**, or run `git worktree add .claude/worktrees/<name> -b <branch>` and `cd` into it before any edit.
> - **Land PRs with `scripts/gh-lars pr merge <n> --rebase --auto`** (rebase only — no squash, no merge commits). PRs require at least 1 human approval before merge; queue them and let the owner approve.
> - **All `gh` issue/PR/comment operations MUST use `scripts/gh-lars`** instead of bare `gh`. Identity is the **`cap-alpha-workflow-automation` GitHub App**. Tokens are minted automatically by `scripts/gh-app-token.sh` using `GH_APP_ID` and `GH_INSTALLATION_ID` from `.env.personas` (gitignored). PEM at `~/.ghconfig/triage-app.pem` on each dev machine (never committed).
> - **Why:** concurrent agents in the same checkout cause branch switches, vanishing edits, and merge conflicts. Worktrees give physical isolation; the merge queue serializes landings and re-runs CI on the combined state.
>
> Established 2026-04-07 after multi-agent coordination failures. One-PR-per-concern rule added 2026-05-06.

---

## Codebase map — read before any task

**[`CODEBASE.md`](CODEBASE.md)** — domain model, key files by concern, BigQuery layout, and a "task → where to look" table. Read it after this file and before opening any source file.

---

## Project overview
NFL contract analytics pipeline + **Pundit Prediction Ledger** (the product). Medallion architecture (bronze/silver/gold) on BigQuery. XGBoost risk model. FastAPI backend. Next.js dashboard.

## Tech stack
- **Python 3.13+** — local venv (`.venv/`) for dev, lint, and tests
- **BigQuery** — sole data warehouse (no DuckDB/MotherDuck)
- **Pipeline**: custom Python ETL in `pipeline/src/`
- **ML**: XGBoost, scikit-learn, SHAP
- **API**: FastAPI (`pipeline/api/`)
- **Frontend**: Next.js (`web/`)
- **CI**: GitHub Actions (`.github/workflows/`)
- **Testing**: pytest (`pipeline/pytest.ini`, `pipeline/tests/`)
- **Docker**: only for Playwright E2E tests and Spotrac scraping

## Execution environment

**Tests and linting run locally via the `.venv/` virtualenv — no Docker required.**

```bash
make setup          # creates venv + configures git hooks (one-time)
make test           # run unit tests
make lint           # check formatting
make check          # lint + test
```

**Docker is only needed for browser-based tasks:**

```bash
make up             # start Docker containers
make test-e2e       # Playwright E2E tests (needs Docker)
make pipeline-scrape # Spotrac scraping via Selenium (needs Docker)
```

## Agent coordination

Multiple agents may run concurrently. The combination of **worktrees + merge queue + locks** prevents stepping on each other:

| Layer | Tool | What it prevents |
|---|---|---|
| File isolation | Git worktrees (`EnterWorktree`) | Concurrent edits to the same checkout |
| Task isolation | `.agent/claim.sh` issue/PR locks | Two agents picking the same issue |
| Landing isolation | GitHub merge queue (`gh pr merge --auto`) | Semantic conflicts at merge time |
| Enforcement | `.claude/hooks/require-worktree.sh` | Edit/Write tools refuse to run in main checkout |

### Protocol

```bash
# 1. Create an isolated worktree (or use the EnterWorktree tool)
git worktree add .claude/worktrees/issue-129 -b feat/129-pundit-roster
cd .claude/worktrees/issue-129

# 2. Check what's currently claimed (run from the worktree)
cat .agent/current.md

# 3. Claim the issue and any shared files you'll edit
.agent/claim.sh claim issue:129 claude-sonnet-<session>
.agent/claim.sh claim file:pipeline/src/assertion_extractor.py claude-sonnet-<session>

# 4. Do your work, commit, push, open the PR

# 5. Before queueing: verify zero non-advisory FAILURE checks
#    Run this and confirm the output is "0". If not, investigate — do NOT merge anyway.
scripts/gh-lars pr view <pr-number> --json statusCheckRollup \
  | jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE" and (.name | test("\\[advisory\\]") | not))] | length'

# 6. Queue the PR for landing — never direct merge. Always rebase.
scripts/gh-lars pr merge <pr-number> --rebase --auto

# 7. After the PR lands on main, release locks
.agent/claim.sh release issue:129 claude-sonnet-<session>
.agent/claim.sh release file:pipeline/src/assertion_extractor.py claude-sonnet-<session>
```

### Advisory vs blocking CI checks

CI check names ending in `[advisory]` are **non-blocking** — their failures are tracked for trends but must not stop a merge. Checks without `[advisory]` are **blocking** and a FAILURE must be investigated and fixed before queueing.

Currently advisory: `Lighthouse audit [advisory]`, `Run E2E Integration Tests (Docker) [advisory]`, dbt tests.

**"CI was red but I merged anyway" is a process violation.** If a non-advisory check is FAILURE, either fix it or escalate — never merge over it.

### Lock semantics
- POSIX-atomic `mkdir` — exactly one concurrent caller wins, others get an immediate error and the holder's identity.
- `current.md` regenerated atomically on every claim/release; `cat .agent/current.md` for an instant snapshot.
- `activity.log` is append-only audit history; entries older than 7 days pruned weekly.
- Stale locks auto-evict after 60 minutes (`STALE_MINUTES` env var to override).
- `claim.sh` refuses to run from the main checkout unless `ALLOW_MAIN_CHECKOUT=1`.

### Agent commit identity
Inside any agent worktree, run `scripts/configure_agent_identity.sh` (or `make agent-identity`) once. This sets the worktree's local git author to `Claude Code (agent) <noreply@anthropic.com>` so commits are attributed to Claude rather than the human user. The PR author on GitHub still reflects whoever owns the `gh` token until a dedicated bot account exists.

### Worktree hygiene
Run `make prune-worktrees` (calls `scripts/prune_worktrees.sh`) periodically to clean up worktrees whose branch has already merged into `main`. Stale worktrees accumulate fast across many agent runs.

### Rebase safety — always fetch PR branch first

**Never** run `git rebase origin/main` + `git push --force-with-lease` without first
fetching the PR branch. Third parties (e.g. `copilot-swe-agent`) may push commits to
the branch between your last local fetch and the force-push; a bare rebase will silently
orphan those commits.

**Always use `scripts/git-rebase-safe.sh <worktree-path> <branch>` instead of a bare
rebase+push.** The script:
1. Fetches `origin/<branch>` to bring the remote tip up to date.
2. Detects any orphaned commits on `origin/<branch>` not yet in local HEAD.
3. Cherry-picks orphans (oldest-first) before rebasing.
4. Rebases onto `origin/main` and pushes with `--force-with-lease`.

Observed failures without this guard: PR #704 (b27cd08), #725 (7c3e697), #729 (3e10cf7).

### Parallel dispatch protocol (prevent API surface collisions)

Worktrees + merge queue prevent *file edit* conflicts. They do **not** prevent
two agents independently creating files with the same name in the same package
— a naming collision at the API surface level that requires a manual semantic
merge.

**Before fanning out N agents on issues from the same design cluster:**

```bash
# 1. Run the pre-flight plan check (read-only, from anywhere)
.agent/claim.sh plan issue:684 issue:685 issue:686 ...

# 2. Claim every namespace the agents will write new files into
.agent/claim.sh orchestrate namespace:pipeline/src/domain_* orchestrator-<session>
.agent/claim.sh orchestrate namespace:pipeline/src/plugins/ orchestrator-<session>

# 3. In each agent's prompt, state explicitly what it OWNS and what to avoid
#    e.g. "OWNS: pipeline/src/domain_plugin.py — do not create domain_protocol.py"

# 4. After all PRs land, release namespace locks
.agent/claim.sh release namespace:pipeline/src/domain_* orchestrator-<session>
```

**Rule:** If two issues in a cluster share a parent issue or touch the same
`pipeline/src/` namespace, claim the namespace before dispatch. One agent per
new module. Serialize agents that must share a file rather than running them
in parallel.

### Shared files (high conflict risk — always claim before editing)
```
pipeline/src/assertion_extractor.py
pipeline/src/cryptographic_ledger.py
pipeline/src/db_manager.py
pipeline/src/domain_plugin.py
pipeline/src/domain_protocol.py
pipeline/src/domain_registry.py
pipeline/config/media_sources.yaml
web/app/layout.tsx
```

## Conventions
- BigQuery only. No DuckDB/MotherDuck references.
- Medallion layers: bronze (raw) → silver (cleaned) → gold (features/aggregates)
- All BigQuery access goes through `pipeline/src/db_manager.py`
- Config via `pipeline/src/config.py` and `pipeline/config/`
- Environment variables for secrets (never hardcode)
- Commit messages: `type(scope): description`
- All SQL must compile natively for BigQuery (`STRING` not `VARCHAR`, `FLOAT64`/`INT64`, `SAFE_CAST` not `TRY_CAST`, `MOD()` not `%`).

## Frontend shipping checklist (mandatory, closes #672)

Before marking any UI/frontend task done, an agent MUST verify all three:

1. **Deploy pipeline fired** — confirm `production.yml` triggered on the merge (check `gh run list --workflow=production.yml --limit=3`). If it didn't fire, run `cd web && vercel --prod` manually.
2. **Change is live at cap-alpha.co** — fetch the changed route and confirm it returns 200 and the feature is present. Use `curl -I https://cap-alpha.co/<route>` or the Vercel MCP `web_fetch_vercel_url` tool.
3. **E2E coverage** — if Playwright tests exist for the changed route, confirm they passed in CI. If no tests exist, file a follow-up issue for coverage (do not block the PR, but do not skip this step).

Skipping this checklist and reporting a frontend task "done" is a process violation.

## Workflows

### /preflight — Run before any PR
```
make check   # lint + unit tests via local venv
```

**Before queuing any PR for merge, confirm CI checks are registered:**
```bash
scripts/gh-lars pr view <N> --json statusCheckRollup | jq '.statusCheckRollup | length'
# Must return > 0. A result of 0 means no CI ran — do NOT merge.

scripts/gh-lars pr view <N> --json statusCheckRollup | jq '[.statusCheckRollup[] | select(.state != "SUCCESS" and .state != "SKIPPED")] | length'
# Must return 0. Any non-SUCCESS/non-SKIPPED check blocks the merge.
```
A PR that runs no CI has no safety net. `pr_sanity.yml` fires unconditionally on every PR to guarantee `statusCheckRollup` is never empty (see issue #735).

### /test — Run the test suite
```
make test
```

### /lint — Format and lint
```
make lint       # check only
make lint-fix   # auto-fix
```

### /test-e2e — Playwright E2E (Docker required)
```
make up
make test-e2e
```

## Working style

### Autonomy defaults
- If multiple paths forward exist and they're roughly equal, pick one. Don't ask.
- Inform the user what you're doing, then do it. Don't wait for permission on routine work.
- Prefer small, focused PRs. One concern per commit.

### Decision authority — what to do without asking
- **Code changes**: refactor, fix bugs, add features described in an issue — just do it.
- **File creation/deletion**: create new modules, tests, migrations as needed.
- **Dependency changes**: add packages to requirements.txt if the task clearly needs them.
- **Git**: create branches, commit, push feature branches. Never force-push or push to main.
- **CI fixes**: if a workflow is broken and the fix is obvious, fix it.

### When to ask the user
- **Product questions** — "should this work like X or Y?"
- **Scope ambiguity** — 1-hour fix vs 1-week feature?
- **External service changes** — new API keys, GCP resources, billing implications.
- **Data model changes** — altering existing BigQuery schemas (adding columns is fine).

## Token discipline — fix it, don't churn on it
- **Fix proactively** — don't leave broken things for the user to discover.
- **Recognize when you're spinning wheels.** 2-3 attempts at the same fix without convergence = stop. Summarize and hand back.
- Diagnose before retrying. Try a *different* approach.
- Stay on target. No speculative refactoring or gold-plating.

## Model selection — auto-applied, no slash command required

Every Agent/subagent dispatch on this project must pick a model by classifying the task. Do not default by reflex.

| Task class | Model | Examples |
|---|---|---|
| **Planning** (architectural, strategic, optimization) | `claude-opus-4-7` | system design, sprint scoping, cost/CI optimization, prompt redesign, validity-logic decisions |
| **Coding + major follow-ups** | `claude-sonnet-4-6` | feature implementation, multi-file edits, real bug fixes, recurring monitors needing reasoning, substantive code review |
| **Triage + minor fixes** | `claude-haiku-4-5-20251001` | counts, log tails, PR-list scans, status reports, single-file typo/lint fixes, label changes |

Rules:
- **Cap concurrent Opus at 1** (parent counts). For fan-out, use Sonnet × N or Haiku × N.
- **Anchor Haiku prompts** with "answer ONLY from tool output" — it hallucinates without grounding.
- **When in doubt between two tiers**, pick the cheaper one and upgrade only if output is visibly inadequate.

**Why:** On 2026-04-26 ~$1,895 burned in 2h with Opus = 79% of spend, mostly routine progress checks Sonnet/Haiku could have done at 5–20× lower cost. The user wants Opus reserved for planning where plan quality compounds, Sonnet for coding, Haiku for cheap status work.

## Extraction-touching PR rules

### Protected paths
Any PR that modifies one or more of these files is an **extraction PR** and must satisfy the rules below:

```
pipeline/src/assertion_extractor.py
pipeline/src/llm_provider.py
pipeline/config/llm_config.yaml
pipeline/migrations/
pipeline/scripts/check_extraction_health.py
```

### Hard requirements for every extraction PR
1. **Real Gemini call required.** The PR must include (or update) an extraction smoke or integration test that executes at least one real LLM call. `--dry-run` alone is not sufficient — dry-run does not exercise the actual model response path.
2. **PR template checkbox must be checked.** The "Extraction risk" section of the PR template must have the smoke/integration test box checked and the test file linked.
3. **CODEOWNERS review.** PRs touching protected paths are subject to CODEOWNERS review (enforced once the smoke test CI job has been green for 2+ consecutive days per issue #597).

### Why
Extraction bugs are silent and expensive: a broken extractor produces zero assertions with no error, causing silent data loss that only shows up days later in pundit score dashboards. A real Gemini call in CI catches prompt regressions, JSON schema mismatches, and provider-level errors that dry-run cannot catch.
