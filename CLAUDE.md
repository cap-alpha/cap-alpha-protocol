# NFL Dead Money / Pundit Prediction Ledger — Agent Instructions

> ## ⚠️ STOP — READ THIS FIRST
>
> **All agent work on this repo MUST happen in a git worktree, and all PRs MUST land via the GitHub merge queue.**
>
> - **Never edit files in the main checkout.** A PreToolUse hook (`.claude/hooks/require-worktree.sh`) blocks Edit/Write/MultiEdit when CWD is the main repo. If you see that error, switch to a worktree.
> - **Use `EnterWorktree` first**, or run `git worktree add .claude/worktrees/<name> -b <branch>` and `cd` into it before any edit.
> - **Land PRs with `gh pr merge <n> --rebase --auto`** (rebase only — no squash, no merge commits).
> - **Why:** concurrent agents in the same checkout cause branch switches, vanishing edits, and merge conflicts. Worktrees give physical isolation; the merge queue serializes landings and re-runs CI on the combined state.
>
> Established 2026-04-07 after multi-agent coordination failures.

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

# 5. Queue the PR for landing — never direct merge
gh pr merge <pr-number> --rebase --auto

# 6. After the PR lands on main, release locks
.agent/claim.sh release issue:129 claude-sonnet-<session>
.agent/claim.sh release file:pipeline/src/assertion_extractor.py claude-sonnet-<session>
```

### Lock semantics
- POSIX-atomic `mkdir` — exactly one concurrent caller wins, others get an immediate error and the holder's identity.
- `current.md` regenerated atomically on every claim/release; `cat .agent/current.md` for an instant snapshot.
- `activity.log` is append-only audit history; entries older than 7 days pruned weekly.
- Stale locks auto-evict after 60 minutes (`STALE_MINUTES` env var to override).
- `claim.sh` refuses to run from the main checkout unless `ALLOW_MAIN_CHECKOUT=1`.

### Shared files (high conflict risk — always claim before editing)
```
pipeline/src/assertion_extractor.py
pipeline/src/cryptographic_ledger.py
pipeline/src/db_manager.py
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

## Workflows

### /preflight — Run before any PR
```
make check   # lint + unit tests via local venv
```

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
