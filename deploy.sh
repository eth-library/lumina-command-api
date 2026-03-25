#!/bin/bash

echo "Deploying to Cloud Run..."

gcloud run deploy lumina-command-api \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --timeout=900 \
  --memory=1Gi

echo "Done!"