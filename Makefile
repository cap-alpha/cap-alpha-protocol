.PHONY: up down pipeline web e2e shell-pipeline check

# -----------------------------------------------------------------------------
# CORE COMMANDS (IMMUTABLE EXECUTION ONLY)
# -----------------------------------------------------------------------------

up:
	docker compose --env-file .env_docker up -d

down:
	docker compose --env-file .env_docker down

shell-pipeline:
	docker compose --env-file .env_docker exec pipeline bash

# -----------------------------------------------------------------------------
# PIPELINE EXECUTION
# -----------------------------------------------------------------------------

pipeline-scrape:
	docker compose --env-file .env_docker exec -e CHROME_BIN=/usr/bin/chromium -e CHROMEDRIVER_BIN=/usr/bin/chromedriver pipeline bash -c "python pipeline/src/spotrac_scraper_v2.py team-cap 2024"

pipeline-train:
	docker compose --env-file .env_docker exec pipeline bash -c "python pipeline/src/train_model.py"

pipeline-nlp:
	@echo "Hydrating 768-D NLP vectors into Silver Layer..."
	docker compose --env-file .env_docker exec pipeline bash -c "python pipeline/src/generate_sentiment_features.py"

pipeline-validate:
	@echo "Running Pipeline Validation Suite (Target Leakage Diagnostics)..."
	docker compose --env-file .env_docker exec pipeline bash -c "python pipeline/scripts/check_target_leakage.py"

# -----------------------------------------------------------------------------
# WEB & TESTING
# -----------------------------------------------------------------------------

web-logs:
	docker compose --env-file .env_docker logs -f web

test-e2e:
	@echo "Running Playwright E2E suite natively inside Ubuntu container..."
	docker compose --env-file .env_docker run --rm e2e
