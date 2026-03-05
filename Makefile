.PHONY: up down pipeline web e2e shell-pipeline check

# -----------------------------------------------------------------------------
# CORE COMMANDS (IMMUTABLE EXECUTION ONLY)
# -----------------------------------------------------------------------------

up:
	docker compose up -d

down:
	docker compose down

shell-pipeline:
	docker compose exec pipeline bash

# -----------------------------------------------------------------------------
# PIPELINE EXECUTION
# -----------------------------------------------------------------------------

pipeline-scrape:
	docker compose exec pipeline bash -c "python src/spotrac_scraper_v2.py team-cap 2024"

pipeline-train:
	docker compose exec pipeline bash -c "python src/train_model.py"

# -----------------------------------------------------------------------------
# WEB & TESTING
# -----------------------------------------------------------------------------

web-logs:
	docker compose logs -f web

test-e2e:
	@echo "Running Playwright E2E suite natively inside Ubuntu container..."
	docker compose run --rm e2e
