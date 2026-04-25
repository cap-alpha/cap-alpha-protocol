# Agent Orientation Cache

> Last updated: 2026-04-25
> Updated by: bootstrap agent (refresh: ruff linter, local venv, post-gitignore)

This file provides shared conventions for all /go agents. Read CLAUDE.md for the authoritative source — this cache distills the most common operations.

---

## Repository summary

NFL contract analytics + **Pundit Prediction Ledger** product. Medallion architecture (bronze→silver→gold) on BigQuery. Python ETL, FastAPI backend, Next.js frontend.

## Branch naming

Agent branches: `worktree-<type>-<issue>-<slug>` (e.g. `worktree-feat-240-parallel-extraction`)
Manual branches: `feat/<issue>-<slug>` or `fix/<slug>`
Worktree dirs: `.claude/worktrees/<slug>/`

## Commit messages

Format: `type(scope): description`
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `spike`, `ops`, `perf`
Scopes: `extract`, `ingest`, `resolve`, `api`, `web`, `ci`, `pipeline`, `schema`, `billing`, `e2e`, `agents`, `backtest`

## PR format

```markdown
## Summary
<bullet points describing changes>

Closes #<issue>

## Test plan
- [x] item

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Landing PRs

Always use the merge queue:
```bash
gh pr merge <number> --squash --auto
```
Never merge directly. Never force-push.

## CI checks

Key workflow: `.github/workflows/ci.yml`
- Python 3.10, `pipeline/requirements-dev.txt`
- Lint: `ruff check` + `ruff format --check`
- Tests: `pytest pipeline/tests/ -v -m "not integration"` (skips API + BQ integration tests)

`claude-review` check FAILS on all PRs (ANTHROPIC_API_KEY not set) — NOT a required check.
E2E Docker tests FAIL (known issue #160) — NOT a required check.

## Running checks locally

```bash
make check      # lint + unit tests (local .venv, no Docker)
make test       # unit tests only
make lint       # ruff check + format check
make lint-fix   # auto-fix with ruff
```

No Docker required for tests/lint — uses local `.venv/`.

## Worktree requirement

All edits MUST happen in a git worktree. Hook blocks Edit/Write in main checkout.

```bash
git worktree add .claude/worktrees/<slug> -b worktree-<slug>
cd .claude/worktrees/<slug>
```

## Claim protocol

### 1. GitHub comment
Post on the issue:
```
🤖 intending to work on this at <UTC timestamp>

— 🤖 `go`
```
Wait ~2 min. Only proceed if your claim is the EARLIEST timestamp.
If prior claim exists: post "🤖 yielding to earlier claim".

### 2. File-level locks (shared files only)
From your worktree:
```bash
.agent/claim.sh claim issue:<n> claude-sonnet-<session>
```

### 3. Done comment
```
🤖 PR #<n> opened and queued for merge: <url>

Changes:
- ...

— 🤖 `go`
```

### Shared files (claim before editing)
- `pipeline/src/assertion_extractor.py`
- `pipeline/src/cryptographic_ledger.py`
- `pipeline/src/db_manager.py`
- `pipeline/config/media_sources.yaml`
- `web/app/layout.tsx`

## Issue selection

**Exclude:** `icebox`, `agent-feedback` labels; active claims (<2h); umbrella issues (#204, #177, #139); external-action issues (#140–141, #149–150).

**Prefer:** `critical-path`, `backend`, `data`, `infrastructure`; clear scope; bug fixes over features.

## Key files

| File | Purpose |
|---|---|
| `pipeline/src/db_manager.py` | All BigQuery access (shared) |
| `pipeline/src/assertion_extractor.py` | LLM extraction (shared) |
| `pipeline/src/cryptographic_ledger.py` | Immutable ledger (shared) |
| `pipeline/src/config.py` | Central config |
| `pipeline/config/media_sources.yaml` | Source/pundit config (shared) |
| `pipeline/src/llm_provider.py` | Pluggable LLM |
| `web/app/layout.tsx` | Next.js root layout (shared) |

## LLM provider

Local Ollama (Qwen 2.5 32B). `ollama serve` must be running for extraction. No cloud API needed.

## BigQuery conventions

- `STRING` not `VARCHAR`, `FLOAT64`/`INT64`, `SAFE_CAST` not `TRY_CAST`, `MOD()` not `%`
- Medallion: `bronze` → `silver` → `gold`
- All BQ access via `pipeline/src/db_manager.py`

## Identity footer

All GitHub comments must end with:
```
— 🤖 `go`
```
