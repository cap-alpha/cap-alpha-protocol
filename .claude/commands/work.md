# Autonomous Work Loop

Execute the highest-priority unblocked work for the NFL Dead Money project.

## Triage Protocol (run every time)

### Phase 0: Housekeeping (before any feature work)
1. **Check for uncommitted changes**: `git diff --stat HEAD`
   - If >5 files changed: stage related files, commit with conventional commit message
   - Use `feat(scope):`, `fix(scope):`, `chore(scope):`, `docs(scope):` prefixes
2. **Check for security issues**: grep Makefile, docker-compose.yml, and .env files for hardcoded secrets (API keys, tokens, passwords)
   - If found: move to `docker_env.txt` references immediately — this is P0
3. **Check for broken tests**: run `make preflight` (if Docker is available) or `pytest pipeline/tests/ -v -m "not integration"` locally
   - If tests fail: fix before any new feature work

### Phase 1: Priority Queue (pick the FIRST unblocked item)
Read `docs/sprints/MASTER_SPRINT_PLAN.md` and pick work in this order:

1. **Failing CI / broken builds** — anything that blocks the main branch
2. **In-progress items `[/]`** — finish what's started before starting new work
3. **Partially-complete sprints** — if a sprint has 4/5 items done, close it out
4. **Items marked `[ ]` in the lowest sprint number** — oldest unfinished work first
5. **Items explicitly tagged `[b]` (blocked)** — skip unless the blocker is something I can resolve

### Phase 2: Execute
For each task:
1. Mark the task `[/]` in MASTER_SPRINT_PLAN.md
2. Read all related files to understand the current state
3. Implement the change (code, config, docs — whatever the task requires)
4. Validate: run tests, check for errors, verify the change works
5. Mark the task `[x]` in MASTER_SPRINT_PLAN.md
6. Commit with a conventional commit message referencing the sprint task ID

### Phase 3: Report
After completing a task (or hitting a blocker), summarize:
- What was done
- What was blocked and why
- What the next priority is

## Rules
- **Do NOT start a new Epic/Sprint without human sign-off**
- **All execution inside Docker** via `make` targets when available
- **All SQL must be BigQuery dialect** (STRING, INT64, FLOAT64, SAFE_CAST, NUMERIC)
- **Never delete skill files** in `.agent/skills/` — they are permanent context
- **Commit early, commit often** — don't let >20 files pile up uncommitted
- **If `docker_env.txt` is missing**, skip Docker-dependent validation but note it in the report

## Current Priority Queue (as of 2026-03-30)

| Priority | Item | Status | Notes |
|----------|------|--------|-------|
| P0 | Hardcoded secrets in Makefile | 🔴 | MotherDuck token + Gemini key exposed in `pipeline-factcheck` |
| P0 | Commit 19-file BigQuery migration | 🔴 | Sitting uncommitted from prior session |
| P1 | SP19-3: Append-only audit tier | ⬜ | Last item in Sprint 19, all others done |
| P1 | SP20-1: Edge caching/SSG | 🟡 | Marked in-progress |
| P2 | SP20-2 through SP20-4 | ⬜ | Performance optimization sprint |
| P3 | SP22: Pundit Prediction Ledger | ⬜ | Major feature, 5 tasks — needs human sign-off |
| P3 | SP26: GitHub Migration | ⬜ | Meta-workflow improvement |
