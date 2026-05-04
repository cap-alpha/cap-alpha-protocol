#!/usr/bin/env bash
# setup_cost_alerts.sh — Create GCP billing budget with Slack alerting
#
# Creates three threshold alerts (50% / 100% / 200%) on the GCP billing
# account linked to this project. Alerts route to Pub/Sub → Cloud Function
# → Slack (or directly via billing notification channel if already wired).
#
# Usage:
#   ./scripts/setup_cost_alerts.sh
#
# Prerequisites:
#   gcloud auth login  (one-time)
#   gcloud config set project cap-alpha-protocol  (one-time)
#   Enable APIs: gcloud services enable billingbudgets.googleapis.com cloudbilling.googleapis.com
#
# Env vars (auto-read from .env.personas if present):
#   GCP_PROJECT_ID        — default: cap-alpha-protocol
#   BILLING_ACCOUNT_ID    — 6-part hex from `gcloud billing accounts list`
#   MONTHLY_BQ_BUDGET_USD — monthly BigQuery budget in USD (default: 20)
#   SLACK_WEBHOOK_URL     — Slack incoming webhook for alert delivery

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source .env.personas if present and vars not already set
if [[ -f "${REPO_ROOT}/.env.personas" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.env.personas"
    set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:-cap-alpha-protocol}"
# Must be set; find via: gcloud billing accounts list
BILLING_ACCOUNT="${BILLING_ACCOUNT_ID:-01811E-06F23B-829FFC}"
MONTHLY_BUDGET="${MONTHLY_BQ_BUDGET_USD:-20}"
SLACK_WEBHOOK="${SLACK_WEBHOOK_URL:-}"
BUDGET_NAME="cap-alpha-bigquery-monthly"

echo "[setup_cost_alerts] Project:         ${PROJECT_ID}"
echo "[setup_cost_alerts] Billing account: ${BILLING_ACCOUNT}"
echo "[setup_cost_alerts] Monthly budget:  \$${MONTHLY_BUDGET} USD"

# 1. Enable required APIs
echo "[setup_cost_alerts] Enabling billing APIs..."
gcloud services enable billingbudgets.googleapis.com cloudbilling.googleapis.com \
    --project="${PROJECT_ID}" --quiet

# 2. Create or update the budget via gcloud billing budgets
#    Three thresholds: 50%, 100%, 200% of budget amount.
#    'spend-basis=CURRENT_SPEND' triggers on actual (not forecasted) spend.

EXISTING=$(gcloud billing budgets list \
    --billing-account="${BILLING_ACCOUNT}" \
    --filter="displayName=${BUDGET_NAME}" \
    --format="value(name)" 2>/dev/null || true)

if [[ -n "${EXISTING}" ]]; then
    echo "[setup_cost_alerts] Budget '${BUDGET_NAME}' already exists — updating..."
    gcloud billing budgets update "${EXISTING}" \
        --billing-account="${BILLING_ACCOUNT}" \
        --display-name="${BUDGET_NAME}" \
        --budget-amount="${MONTHLY_BUDGET}USD" \
        --threshold-rule=percent=0.5,basis=CURRENT_SPEND \
        --threshold-rule=percent=1.0,basis=CURRENT_SPEND \
        --threshold-rule=percent=2.0,basis=CURRENT_SPEND
else
    echo "[setup_cost_alerts] Creating budget '${BUDGET_NAME}'..."
    gcloud billing budgets create \
        --billing-account="${BILLING_ACCOUNT}" \
        --display-name="${BUDGET_NAME}" \
        --budget-amount="${MONTHLY_BUDGET}USD" \
        --threshold-rule=percent=0.5,basis=CURRENT_SPEND \
        --threshold-rule=percent=1.0,basis=CURRENT_SPEND \
        --threshold-rule=percent=2.0,basis=CURRENT_SPEND
fi

echo "[setup_cost_alerts] Budget configured:"
gcloud billing budgets list \
    --billing-account="${BILLING_ACCOUNT}" \
    --filter="displayName=${BUDGET_NAME}" \
    --format="table(displayName, amount.specifiedAmount.units, thresholdRules.thresholdPercent)"

# 3. Slack notification via Pub/Sub (best-effort — requires Pub/Sub + Cloud Function)
#    This step is skipped if SLACK_WEBHOOK_URL is not set.
if [[ -z "${SLACK_WEBHOOK}" ]]; then
    echo "[setup_cost_alerts] SLACK_WEBHOOK_URL not set — skipping Pub/Sub wiring."
    echo "  To enable Slack alerts, set SLACK_WEBHOOK_URL and re-run this script."
    echo "  Or configure via GCP Console: Billing → Budgets & Alerts → Manage notifications."
else
    echo "[setup_cost_alerts] SLACK_WEBHOOK_URL found — to complete Slack wiring:"
    echo "  1. GCP Console → Billing → Budgets & Alerts → '${BUDGET_NAME}'"
    echo "  2. Under 'Manage notifications', connect a Pub/Sub topic"
    echo "  3. Deploy a Cloud Function that POSTs to SLACK_WEBHOOK_URL on Pub/Sub messages"
    echo "  OR: Use a third-party connector (e.g. Zapier / n8n / custom Cloud Function)."
    echo ""
    echo "  Quick Cloud Run one-liner (requires billing-alerts-topic to exist):"
    echo "    gcloud pubsub topics create billing-alerts"
    echo "    # Then wire the budget to that topic via GCP Console"
fi

echo ""
echo "[setup_cost_alerts] Done. Alerts at 50%/100%/200% of \$${MONTHLY_BUDGET}/month are active."
echo "  Verify: https://console.cloud.google.com/billing/${BILLING_ACCOUNT}/budgets"
