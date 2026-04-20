#!/bin/bash

echo "Deploying to Cloud Run..."

gcloud run deploy lumina-command-api \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --timeout=3600 \
  --memory=8Gi \
  --cpu=4 \
  --set-secrets=OPENAI_API_KEY=OPENAI_API_KEY:latest,PINECONE_API_KEY=PINECONE_API_KEY:latest

echo "Done!"