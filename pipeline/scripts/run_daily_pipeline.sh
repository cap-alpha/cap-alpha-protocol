#!/bin/bash
# Daily Pundit Prediction Ledger Pipeline
# Invoked by launchd (com.punditledger.pipeline) at 6:00 AM local time.
# Logs to /tmp/pundit_pipeline.log (appended each run).
#
# Stages:
#   1. media_ingestor     — ingest new articles from RSS feeds
#   2. assertion_extractor — extract predictions via local Ollama (qwen2.5:32b)
#   3. resolve_daily      — resolve PENDING predictions against outcomes

set -euo pipefail

REPO_ROOT="/Users/andrewsmith/portfolio/nfl-dead-money"
PIPELINE_DIR="${REPO_ROOT}/pipeline"
PYTHON="${REPO_ROOT}/.venv/bin/python"
ENV_FILE="${REPO_ROOT}/.env"
LOG_FILE="/tmp/pundit_pipeline.log"

echo "=== Pundit Pipeline run started at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "${LOG_FILE}"

# Load environment variables from .env (BigQuery credentials, API keys, etc.)
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
else
    echo "WARNING: ${ENV_FILE} not found; continuing without it" >> "${LOG_FILE}"
fi

# All pipeline modules use relative imports from within pipeline/
cd "${PIPELINE_DIR}"

run_stage() {
    local stage="$1"
    shift
    echo "--- [$(date -u +%H:%M:%SZ)] Stage: ${stage} ---" >> "${LOG_FILE}"
    if "${PYTHON}" "$@" >> "${LOG_FILE}" 2>&1; then
        echo "--- [$(date -u +%H:%M:%SZ)] ${stage} OK ---" >> "${LOG_FILE}"
    else
        local rc=$?
        echo "--- [$(date -u +%H:%M:%SZ)] ${stage} FAILED (exit ${rc}) ---" >> "${LOG_FILE}"
        # Exit so launchd records a non-zero exit and throttle kicks in
        exit "${rc}"
    fi
}

run_stage "media_ingestor"      -m src.media_ingestor
run_stage "assertion_extractor" -m src.assertion_extractor --limit 500
run_stage "resolve_daily"       -m src.resolve_daily

echo "=== Pundit Pipeline completed successfully at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "${LOG_FILE}"
