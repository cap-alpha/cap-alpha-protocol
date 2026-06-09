.PHONY: up down shell-pipeline venv web-install test lint lint-fix test-e2e pipeline-scrape pipeline-train pipeline-nlp pipeline-validate pipeline-factcheck web-logs setup check type-check resolve-draft resolve-draft-dry setup-triage-agent uninstall-triage-agent agent-identity prune-worktrees backfill-silver-v2 backfill-entities dev-api dev-seed regen-snapshot

PYTHON ?= python3
# Resolve VENV to the main repo root — works from both the main checkout and worktrees.
REPO_ROOT := $(shell cd "$$(git rev-parse --git-common-dir)/.." && pwd)
VENV := $(REPO_ROOT)/.venv
ACTIVATE := . $(VENV)/bin/activate
PY := $(ACTIVATE) &&

# Docker — only needed for E2E, scraping, and pipeline orchestration
DOCKER := docker compose --env-file docker_env.txt

# -----------------------------------------------------------------------------
# SETUP
# -----------------------------------------------------------------------------

setup: venv web-install
	git config core.hooksPath .githooks
	@echo "Done. Venv at $(VENV)/, git hooks configured."

web-install:
	cd web && npm install

setup-triage-agent:
	bash scripts/setup-triage-agent.sh

uninstall-triage-agent:
	bash scripts/uninstall-triage-agent.sh

agent-identity:
	bash scripts/configure_agent_identity.sh

prune-worktrees:
	bash scripts/prune_worktrees.sh

venv:
	$(PYTHON) -m venv $(VENV)
	$(PY) pip install --upgrade pip
	$(PY) pip install -r pipeline/requirements-dev.txt
	@echo ""
	@echo "Venv ready. Activate: source $(VENV)/bin/activate"

# -----------------------------------------------------------------------------
# LOCAL DEV — lint + test via venv (no Docker required)
# -----------------------------------------------------------------------------

test:
	$(PY) PYTHONPATH=$${PYTHONPATH:+$$PYTHONPATH:}$$(pwd)/pipeline \
		python -m pytest pipeline/tests/ -v --tb=short \
		-m "not integration" \
		--ignore=pipeline/tests/test_api.py \
		--ignore=pipeline/tests/test_api_vegas.py \
		--ignore=pipeline/tests/test_ledger_bq_integration.py

lint:
	$(PY) ruff check pipeline/src/ pipeline/tests/ && \
		ruff format --check pipeline/src/ pipeline/tests/

lint-fix:
	$(PY) ruff check --fix pipeline/src/ pipeline/tests/ && \
		ruff format pipeline/src/ pipeline/tests/

check: lint test

type-check:
	cd web && npx tsc --noEmit

# -----------------------------------------------------------------------------
# AGENT HOUSEKEEPING
# -----------------------------------------------------------------------------

prune-worktrees:
	./scripts/prune_worktrees.sh

agent-identity:
	./scripts/configure_agent_identity.sh

# -----------------------------------------------------------------------------
# DOCKER — scraping, E2E, pipeline orchestration
# -----------------------------------------------------------------------------

up:
	$(DOCKER) up -d

down:
	$(DOCKER) down

shell-pipeline:
	$(DOCKER) exec pipeline bash

test-e2e:
	@echo "Running Playwright E2E suite in Docker..."
	$(DOCKER) run --rm e2e

pipeline-scrape:
	$(DOCKER) exec -e CHROME_BIN=/usr/bin/chromium -e CHROMEDRIVER_BIN=/usr/bin/chromedriver pipeline bash -c "python pipeline/src/spotrac_scraper_v2.py team-cap && python pipeline/src/spotrac_scraper_v2.py player-salaries && python pipeline/src/spotrac_scraper_v2.py player-rankings && python pipeline/src/spotrac_scraper_v2.py player-contracts"

pipeline-train:
	$(DOCKER) exec pipeline bash -c "python pipeline/src/train_model.py"

pipeline-nlp:
	@echo "Hydrating 768-D NLP vectors into Silver Layer..."
	$(DOCKER) exec pipeline bash -c "python pipeline/src/generate_sentiment_features.py"

pipeline-validate:
	@echo "Running Pipeline Validation Suite (Target Leakage Diagnostics)..."
	$(DOCKER) exec pipeline bash -c "python pipeline/scripts/check_target_leakage.py"

pipeline-factcheck:
	@echo "Running Automated Gemini Search Grounding on Top 50 Predictions..."
	$(DOCKER) exec -e GEMINI_MODEL="$(if $(MODEL),$(MODEL),gemini-2.5-flash)" pipeline bash -c "python scripts/fact_check_top_50.py $(if $(TEAM),\"$(TEAM)\",)"

# -----------------------------------------------------------------------------
# RESOLUTION — run locally with GCP credentials (no Docker required)
# Set GCP_PROJECT_ID in your environment (or source docker_env.txt first).
# -----------------------------------------------------------------------------

resolve-draft-dry:
	@echo "Dry-run: draft_pick resolution pass (no writes)..."
	$(PY) PYTHONPATH=$$(pwd)/pipeline \
		python -m src.resolve_daily --category draft_pick --dry-run

resolve-draft:
	@echo "Running draft_pick resolution pass..."
	$(PY) PYTHONPATH=$$(pwd)/pipeline \
		python -m src.resolve_daily --category draft_pick

# -----------------------------------------------------------------------------
# SILVER V2 — backfill + migration
# -----------------------------------------------------------------------------

backfill-silver-v2:
	$(PY) python pipeline/scripts/backfill_silver_v2_sample.py

backfill-entities:
	@echo "Backfilling entities table from prediction_ledger..."
	$(PY) DB_BACKEND=duckdb DUCKDB_PATH=$(REPO_ROOT)/pipeline/data/local.duckdb \
		PYTHONPATH=$(REPO_ROOT)/pipeline \
		python -m src.backfill_entities

# -----------------------------------------------------------------------------
# LOCAL DEV — FastAPI + DuckDB, no GCP required
# -----------------------------------------------------------------------------

LOCAL_DUCKDB := $(REPO_ROOT)/pipeline/data/local.duckdb

dev-seed: ## Init local DuckDB schema and load golden seed predictions
	@mkdir -p $(REPO_ROOT)/pipeline/data
	@rm -f $(LOCAL_DUCKDB)
	$(PY) USE_LOCAL_DB=1 LOCAL_DB_PATH=$(LOCAL_DUCKDB) \
		PYTHONPATH=$(CURDIR)/pipeline \
		python -c "from src.db_manager import DBManager; db = DBManager(); print('[dev-seed] schema ready at $(LOCAL_DUCKDB)'); db.close()"
	$(PY) DUCKDB_PATH=$(LOCAL_DUCKDB) \
		python $(CURDIR)/pipeline/scripts/load_golden_seed.py

dev-api: ## Start FastAPI locally with DuckDB backend — no BQ or GCP needed
	@echo "Starting local API at http://localhost:8000 (DuckDB: $(LOCAL_DUCKDB))"
	@echo "Run 'make dev-seed' first if the leaderboard is empty."
	$(PY) USE_LOCAL_DB=1 API_AUTH_DISABLED=1 MIN_RESOLVED_CLAIMS=1 \
		LOCAL_DB_PATH=$(LOCAL_DUCKDB) PYTHONPATH=$(CURDIR)/pipeline \
		uvicorn pipeline.api.main:app --reload --reload-dir $(CURDIR)/pipeline --port 8000

# -----------------------------------------------------------------------------
# WEB
# -----------------------------------------------------------------------------

web-logs:
	$(DOCKER) logs -f web

# -----------------------------------------------------------------------------
# SNAPSHOT — regenerate static data files
# -----------------------------------------------------------------------------

regen-snapshot: ## Regenerate leaderboard snapshot from BigQuery (writes web/app/lib/data/leaderboard-snapshot.json)
	$(VENV)/bin/python pipeline/scripts/regen_leaderboard_snapshot.py
