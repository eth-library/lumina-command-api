#!/bin/bash

# Reads OPENAI_API_KEY, PINECONE_API_KEY and INTERNAL_API_KEY from .env
# and creates/updates them in Google Cloud Secret Manager.

set -e

ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ .env file not found."
  exit 1
fi

echo "📂 Reading $ENV_FILE..."

SECRETS=("OPENAI_API_KEY" "PINECONE_API_KEY" "INTERNAL_API_KEY")

for SECRET_NAME in "${SECRETS[@]}"; do
  echo "🔍 Looking for $SECRET_NAME in $ENV_FILE..."
  VALUE=$(grep "^${SECRET_NAME}=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '\r\n')

  if [ -z "$VALUE" ]; then
    echo "⚠️  $SECRET_NAME is empty or not set in .env — skipping."
    continue
  fi

  echo "✔  Found $SECRET_NAME, checking Secret Manager..."

  # Create secret if it doesn't exist yet
  if ! gcloud secrets describe "$SECRET_NAME" 2>/dev/null; then
    echo "🔐 Creating secret: $SECRET_NAME"
    gcloud secrets create "$SECRET_NAME" --replication-policy="automatic"
  fi

  # Add a new version with the current value
  echo "📤 Uploading $SECRET_NAME to Secret Manager..."
  echo -n "$VALUE" | gcloud secrets versions add "$SECRET_NAME" --data-file=-
  echo "✅ $SECRET_NAME updated in Secret Manager."
done

echo ""
echo "Done! You can now deploy with ./deploy.sh"
