.PHONY: up down shell-pipeline venv test lint lint-fix test-e2e pipeline-scrape pipeline-train pipeline-nlp pipeline-validate pipeline-factcheck web-logs setup check prune-worktrees agent-identity

PYTHON ?= python3
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate
PY := $(ACTIVATE) &&

# Docker — only needed for E2E, scraping, and pipeline orchestration
DOCKER := docker compose --env-file docker_env.txt

# -----------------------------------------------------------------------------
# SETUP
# -----------------------------------------------------------------------------

setup: venv
	git config core.hooksPath .githooks
	@echo "Done. Venv at $(VENV)/, git hooks configured."

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
# WEB
# -----------------------------------------------------------------------------

web-logs:
	$(DOCKER) logs -f web
