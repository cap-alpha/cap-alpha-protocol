#!/usr/bin/env bash
# deploy/deploy-api.sh — Build and deploy pundit-api to Cloud Run
# Usage: ./deploy/deploy-api.sh [image-tag]
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-my-project-1525668581184}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="pundit-api"
IMAGE_TAG="${1:-latest}"
IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/pundit-api/api:${IMAGE_TAG}"
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
  --min-instances 0 \
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
