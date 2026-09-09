#!/bin/bash

echo "Deploying to Cloud Run..."

gcloud run deploy lumina-command-api \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --timeout=3600 \
  --memory=8Gi \
  --cpu=4 \
  --max-instances=3 \
  --set-secrets=OPENAI_API_KEY=OPENAI_API_KEY:latest,PINECONE_API_KEY=PINECONE_API_KEY:latest,INTERNAL_API_KEY=INTERNAL_API_KEY:latest \
  --update-env-vars=APP_ENV=production,PREFECT_API_URL=http://lumina-box01.ethz.ch:4200/api

echo "Done!"