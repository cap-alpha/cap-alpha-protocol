# Agent Orientation Cache

> Last updated: 2026-04-23
> Updated by: bootstrap agent

This file provides shared conventions and operational guidance for all agents working on this repo. Read CLAUDE.md for the authoritative source — this cache distills the most common operations.

---

## Repository summary

NFL contract analytics pipeline + **Pundit Prediction Ledger** product. Medallion architecture (bronze→silver→gold) on BigQuery. Python ETL pipeline, FastAPI backend, Next.js frontend.

## Branch naming

Pattern: `feat/<issue>-<slug>` or `fix/<issue>-<slug>`

Examples from recent history:
- `feat/124-scoring-methodology-v2`
- `fix/170-target-player-name`
- `worktree-llm-provider-178`
- `feat/142-api-key-data-model`

## Commit messages

Format: `type(scope): description`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `spike`
Scopes: `extract`, `ingest`, `resolve`, `api`, `web`, `ci`, `pipeline`, `schema`, `billing`, `e2e`

## PR format

```markdown
## Summary
<bullet points describing changes>

Closes #<issue>

## Test plan
- [x] item
- [ ] item

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Landing PRs

**Always** use the merge queue:
```bash
gh pr merge <number> --squash --auto
```
Never merge directly. Never force-push.

## CI checks

CI runs on `push`, `pull_request`, and `merge_group` events against `main`.

Key workflow: `.github/workflows/ci.yml`
- Python 3.10, installs from `pipeline/requirements.txt`
- Runs `pytest pipeline/tests/ -v -m "not integration"` (skips API tests)

Other workflows: `tests.yml`, `canary.yml`, `frontend_preflight.yml`, `deploy.yml`, `production.yml`

## Running tests locally

```bash
# Unit tests (in Docker)
make up
docker compose --env-file docker_env.txt exec pipeline bash -c "python -m pytest pipeline/tests/ -v --tb=short"

# Linting (local Python is fine)
black --check pipeline/src/
isort --check pipeline/src/
flake8 pipeline/src/
```

## Worktree requirement

All edits MUST happen in a git worktree. A PreToolUse hook blocks Edit/Write in the main checkout.

```bash
# Use EnterWorktree tool, or manually:
git worktree add .claude/worktrees/<name> -b <branch>
cd .claude/worktrees/<name>
```

## Claim protocol

Before working on an issue, post a claim comment:
```
🤖 intending to work on this at <UTC timestamp>
```
Wait ~2 minutes, re-read comments. Only proceed if your claim is earliest.

When done or blocked, post:
```
🤖 releasing issue
```

Also use `.agent/claim.sh` for file-level locks on shared files:
- `pipeline/src/assertion_extractor.py`
- `pipeline/src/cryptographic_ledger.py`
- `pipeline/src/db_manager.py`
- `pipeline/config/media_sources.yaml`
- `web/app/layout.tsx`

## Issue selection criteria

**Exclude:**
- `icebox` label
- `agent-feedback` label
- Issues with active claims (<2h old)
- Master/tracking issues (#177, #139)
- Issues requiring external actions (Stripe setup, legal, billing accounts)

**Prefer:**
- Clear scope, small surface area
- `backend`, `data`, `infrastructure` labels
- Bug fixes over new features when both available

## Labels to know

| Label | Meaning |
|---|---|
| `critical-path` | Blocks release |
| `icebox` | Deprioritized — skip |
| `product` | Product requirement |
| `monetization` | Revenue features |
| `data` | Data pipeline |
| `infrastructure` | Backend/DevOps |
| `backend` | Server-side logic |

## Key files

| File | Purpose |
|---|---|
| `pipeline/src/db_manager.py` | All BigQuery access (shared — claim before editing) |
| `pipeline/src/assertion_extractor.py` | LLM-based prediction extraction (shared) |
| `pipeline/src/cryptographic_ledger.py` | Immutable ledger (shared) |
| `pipeline/src/config.py` | Central configuration |
| `pipeline/config/media_sources.yaml` | Source/pundit config (shared) |
| `pipeline/config/llm_config.yaml` | LLM provider selection |
| `pipeline/src/llm_provider.py` | Pluggable LLM abstraction |
| `web/app/layout.tsx` | Next.js root layout (shared) |

## BigQuery conventions

- `STRING` not `VARCHAR`, `FLOAT64`/`INT64`, `SAFE_CAST` not `TRY_CAST`, `MOD()` not `%`
- All SQL must compile natively for BigQuery
- Medallion layers: `bronze` (raw) → `silver` (cleaned) → `gold` (features/aggregates)

## Currently open PRs (as of 2026-04-23)

These issues/branches are actively being worked — avoid conflicts:
- #184 — fix/160-e2e-clerk-resilience
- #183 — feat/178-llm-provider-abstraction
- #176 — fix/169-resolution-engine-v2
- #174 — fix/168-extractor-quality-v2
- #173 — fix/167-pipeline-fail-loud-v2
- #172 — fix/166-pundit-matching
- #165 — feat/146-147-stripe-integration
- #164 — feat/144-rate-limiting
- #161 — fix/160-e2e-tests
- #159 — feat/158-pundit-assertion-spike
