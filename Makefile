.PHONY: up down pipeline web e2e shell-pipeline check preflight test test-unit lint help

# -----------------------------------------------------------------------------
# PREFLIGHT & VALIDATION
# -----------------------------------------------------------------------------

preflight: lint test-unit dbt-compile
	@echo "\n✅ Preflight passed. Safe to commit."

lint:
	@echo "Running lint (black --check + isort --check)..."
	docker compose --env-file docker_env.txt exec pipeline bash -c "black --check pipeline/src/ && isort --check-only pipeline/src/"

test-unit:
	@echo "Running unit tests (pytest, no integration)..."
	docker compose --env-file docker_env.txt exec pipeline bash -c "PYTHONPATH=pipeline/libs:pipeline/src pytest pipeline/tests/ -v -m 'not integration'"

test:
	@echo "Running full test suite..."
	docker compose --env-file docker_env.txt exec pipeline bash -c "PYTHONPATH=pipeline/libs:pipeline/src pytest pipeline/tests/ -v"

dbt-compile:
	@echo "Checking dbt SQL compilation (syntax validation)..."
	docker compose --env-file docker_env.txt exec pipeline bash -c "cd dbt && dbt compile --profiles-dir . --project-dir ."

help:
	@echo "NFL Dead Money - Available Commands"
	@echo "===================================="
	@echo "  make preflight        - Run lint + unit tests + dbt compile (pre-commit gate)"
	@echo "  make lint             - Check code formatting (black, isort)"
	@echo "  make test-unit        - Run unit tests only (fast)"
	@echo "  make test             - Run full test suite (unit + integration)"
	@echo "  make dbt-compile      - Validate dbt SQL syntax"
	@echo "  make up               - Start all Docker services"
	@echo "  make down             - Stop all Docker services"
	@echo "  make pipeline-scrape  - Run full Spotrac scraping pipeline"
	@echo "  make pipeline-train   - Train XGBoost risk model"
	@echo "  make pipeline-nlp     - Hydrate NLP sentiment vectors"
	@echo "  make pipeline-validate - Run target leakage diagnostics"
	@echo "  make test-e2e         - Run Playwright E2E tests"
	@echo "  make shell-pipeline   - Shell into pipeline container"

# -----------------------------------------------------------------------------
# CORE COMMANDS (IMMUTABLE EXECUTION ONLY)
# -----------------------------------------------------------------------------

up:
	docker compose --env-file docker_env.txt up -d

down:
	docker compose --env-file docker_env.txt down

shell-pipeline:
	docker compose --env-file docker_env.txt exec pipeline bash

# -----------------------------------------------------------------------------
# PIPELINE EXECUTION
# -----------------------------------------------------------------------------

pipeline-scrape:
	docker compose --env-file docker_env.txt exec -e CHROME_BIN=/usr/bin/chromium -e CHROMEDRIVER_BIN=/usr/bin/chromedriver pipeline bash -c "python pipeline/src/spotrac_scraper_v2.py team-cap && python pipeline/src/spotrac_scraper_v2.py player-salaries && python pipeline/src/spotrac_scraper_v2.py player-rankings && python pipeline/src/spotrac_scraper_v2.py player-contracts"

pipeline-train:
	docker compose --env-file docker_env.txt exec pipeline bash -c "python pipeline/src/train_model.py"

pipeline-nlp:
	@echo "Hydrating 768-D NLP vectors into Silver Layer..."
	docker compose --env-file docker_env.txt exec pipeline bash -c "python pipeline/src/generate_sentiment_features.py"

pipeline-validate:
	@echo "Running Pipeline Validation Suite (Target Leakage Diagnostics)..."
	docker compose --env-file docker_env.txt exec pipeline bash -c "python pipeline/scripts/check_target_leakage.py"

pipeline-factcheck:
	@echo "Running Automated Gemini Search Grounding on Top 50 Predictions..."
	@echo "(Requires MOTHERDUCK_TOKEN and GEMINI_API_KEY in docker_env.txt)"
	docker compose --env-file docker_env.txt exec -e GEMINI_MODEL="$(if $(MODEL),$(MODEL),gemini-2.5-flash)" pipeline bash -c "python scripts/fact_check_top_50.py $(if $(TEAM),\"$(TEAM)\",)"

# -----------------------------------------------------------------------------
# WEB & TESTING
# -----------------------------------------------------------------------------

web-logs:
	docker compose --env-file docker_env.txt logs -f web

test-e2e:
	@echo "Running Playwright E2E suite natively inside Ubuntu container..."
	docker compose --env-file docker_env.txt run --rm e2e
