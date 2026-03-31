.PHONY: up down pipeline web e2e shell-pipeline check

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
	docker compose --env-file docker_env.txt exec -e GEMINI_MODEL="$(if $(MODEL),$(MODEL),gemini-2.5-flash)" pipeline bash -c "python scripts/fact_check_top_50.py $(if $(TEAM),\"$(TEAM)\",)"

# -----------------------------------------------------------------------------
# WEB & TESTING
# -----------------------------------------------------------------------------

web-logs:
	docker compose --env-file docker_env.txt logs -f web

test-e2e:
	@echo "Running Playwright E2E suite natively inside Ubuntu container..."
	docker compose --env-file docker_env.txt run --rm e2e
