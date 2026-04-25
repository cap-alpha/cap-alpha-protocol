#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/cap-alpha-pipeline"
JOB_NAME="cap-alpha-daily-pipeline"

echo "Current GCP Project: $PROJECT_ID"
echo "Building image $IMAGE_NAME..."

# Build the container image using Cloud Build
gcloud builds submit --tag $IMAGE_NAME -f Dockerfile.cloudrun .

echo "Deploying to Cloud Run Jobs..."

# Attempt to extract secrets from web/.env.local
ENV_VARS_FLAG="PYTHONUNBUFFERED=1"
if [ -f "web/.env.local" ]; then
    echo "Found web/.env.local! Extracting GEMINI_API_KEY..."
    GEMINI_API_KEY=$(grep '^GEMINI_API_KEY=' web/.env.local | cut -d "=" -f 2- | tr -d '"' | tr -d "'")
    POSTGRES_URL=$(grep '^POSTGRES_URL=' web/.env.local | cut -d "=" -f 2- | tr -d '"' | tr -d "'")

    if [ ! -z "$GEMINI_API_KEY" ]; then
        ENV_VARS_FLAG="${ENV_VARS_FLAG},GEMINI_API_KEY=${GEMINI_API_KEY}"
    fi
    if [ ! -z "$POSTGRES_URL" ]; then
        ENV_VARS_FLAG="${ENV_VARS_FLAG},POSTGRES_URL=${POSTGRES_URL}"
    fi
else
    echo "WARNING: web/.env.local not found. You may need to specify secrets manually."
fi

gcloud run jobs create $JOB_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --max-retries 1 \
    --task-timeout 45m \
    --memory 2Gi \
    --cpu 1 \
    --set-env-vars="${ENV_VARS_FLAG}"

echo "Cloud Run Job '$JOB_NAME' created successfully."
echo "To trigger the job manually: gcloud run jobs execute $JOB_NAME"
echo ""
echo "To create the Cloud Scheduler trigger (Daily at 2 AM UTC):"
echo "gcloud scheduler jobs create http cap-alpha-scheduler \\"
echo "  --schedule=\"0 2 * * *\" \\"
echo "  --uri=\"https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run\" \\"
echo "  --http-method=POST \\"
echo "  --oauth-service-account-email=(your-compute-service-account-email)"
