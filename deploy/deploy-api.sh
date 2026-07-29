#!/usr/bin/env bash
# deploy/deploy-api.sh — Manual escape-hatch build+deploy of pundit-ledger-api
# to Cloud Run. Normal path is automated: .github/workflows/deploy_api.yml
# runs `gcloud builds submit --config cloudbuild-api.yaml` on every push to
# main touching pipeline/api/**. Use this script only if CI is down and you
# need to hand-deploy (see issue #1183 for the original manual recovery).
#
# Project/service/image values below MUST match cloudbuild-api.yaml — they
# were previously out of sync (my-project-1525668581184 / pundit-api), which
# meant a "successful" run of this script silently deployed nothing that
# users could see (issue #1183).
#
# Usage: ./deploy/deploy-api.sh [image-tag]
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-cap-alpha-protocol}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="pundit-ledger-api"
IMAGE_TAG="${1:-latest}"
IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/pundit-ledger/api:${IMAGE_TAG}"
SA="pundit-api@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> Configuring Docker auth..."
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

echo "==> Building image: ${IMAGE}"
docker build -f Dockerfile.api -t "${IMAGE}" .

echo "==> Pushing image..."
docker push "${IMAGE}"

echo "==> Deploying to Cloud Run (${SERVICE_NAME}) in ${REGION}..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --service-account "${SA}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 10 \
  --concurrency 80 \
  --timeout 60 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --quiet

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format="value(status.url)")

echo ""
echo "==> Deployed: ${URL}"
echo "==> Health check..."
curl -sf "${URL}/" | python3 -m json.tool
