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
	docker compose --env-file docker_env.txt exec -e CHROME_BIN=/usr/bin/chromium -e CHROMEDRIVER_BIN=/usr/bin/chromedriver pipeline bash -c "python pipeline/src/spotrac_scraper_v2.py team-cap 2024"

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
	docker compose exec -e MOTHERDUCK_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImFuZHJldy5wYXRyaWNrLnNtaXRoQGljbG91ZC5jb20iLCJtZFJlZ2lvbiI6ImF3cy11cy1lYXN0LTEiLCJzZXNzaW9uIjoiYW5kcmV3LnBhdHJpY2suc21pdGguaWNsb3VkLmNvbSIsInBhdCI6IndaSkdSa2x3WVJNU3FpbjdLdXJZYXNXTHpmaG9peGhLX1p4c1RwRmFSbDgiLCJ1c2VySWQiOiJmOTM0MjI4Ni04NDNhLTQ5ZTctYTI1My1kOTU2YmU5NjM3OTMiLCJpc3MiOiJtZF9wYXQiLCJyZWFkT25seSI6ZmFsc2UsInRva2VuVHlwZSI6InJlYWRfd3JpdGUiLCJpYXQiOjE3NzM1MTM5ODN9.yRpp_mw929DqO9_DzYe55BIjUAw2q9-gAhc322_5iR8" -e GEMINI_API_KEY="AIzaSyDv0cMQwS-EMgMKF2CB3iiNWQd4rLTzw3E" -e GEMINI_MODEL="$(if $(MODEL),$(MODEL),gemini-2.5-flash)" pipeline bash -c "python scripts/fact_check_top_50.py $(if $(TEAM),\"$(TEAM)\",)"

# -----------------------------------------------------------------------------
# WEB & TESTING
# -----------------------------------------------------------------------------

web-logs:
	docker compose --env-file docker_env.txt logs -f web

test-e2e:
	@echo "Running Playwright E2E suite natively inside Ubuntu container..."
	docker compose --env-file docker_env.txt run --rm e2e
