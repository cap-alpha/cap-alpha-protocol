.PHONY: setup shell pipeline test clean

setup:
	@mkdir -p .docker_buildx
	BUILDX_CONFIG=$$(pwd)/.docker_buildx docker-compose build

shell:
	docker-compose run --rm pipeline /bin/bash

# Run the full pipeline inside the container
pipeline:
	docker-compose run --rm pipeline python3 run_pipeline.py

# Run tests inside the container
test:
	docker-compose run --rm pipeline pytest tests/

validate:
	docker-compose run --rm pipeline python pipeline/src/dead_money_validator.py

clean:
	docker-compose down -v

# Deploy local: Run pipeline -> Copy Data -> Ready for Web Dev
deploy-local: pipeline
	@echo "Deploying data to web app..."
	@mkdir -p web/data
	@cp data/roster_dump.json web/data/roster_dump.json
	@echo "✅ Data Deployed to web/data/roster_dump.json"
