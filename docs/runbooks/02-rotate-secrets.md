# 02 — Rotate a secret

**Audience:** team member with `roles/secretmanager.admin` and deploy rights
**When:** scheduled rotation; suspected leak; developer offboarding; lost or stolen laptop
**Duration:** 10 minutes for `OPENAI_API_KEY` / `PINECONE_API_KEY`; longer for
`INTERNAL_API_KEY`, which needs an Apigee change in the same window

> **Read this first.** Cloud Run resolves `:latest` **when a revision is created**, not per request
> ([ADR 0006](../adr/0006-secrets-in-secret-manager.md)). Adding a secret version changes nothing
> until you redeploy. Every rotation ends with a deploy.

## Prerequisites

- `gcloud` authenticated against the target project
- Local `.env` present at the repository root — `setup-secrets.sh` reads from it and will exit if
  it is missing
- The new credential value, already issued in the provider's console
- **For `INTERNAL_API_KEY` only:** access to the Apigee X configuration, or a colleague who has it,
  available *now* rather than later

## Variables

```bash
export PROJECT_ID="$(gcloud config get-value project)"
export SERVICE="lumina-command-api"
export REGION="europe-west6"
export SECRET_NAME="OPENAI_API_KEY"   # or PINECONE_API_KEY, or INTERNAL_API_KEY
```

## Steps

1. **Issue the new credential** in the provider's console (OpenAI, Pinecone). For
   `INTERNAL_API_KEY`, generate one locally:
   ```bash
   openssl rand -base64 32
   ```
   **Do not revoke the old credential yet.** It stays valid until verification passes.

2. **Record the current secret version**, so you can roll back to a known-good value.
   ```bash
   gcloud secrets versions list "$SECRET_NAME" --limit 3
   ```

3. **Update the local `.env`** with the new value. It is the input to the next step.

4. **Push to Secret Manager.**
   ```bash
   ./setup-secrets.sh
   ```
   This adds a **new version** of all three secrets from `.env` — including the two you did not
   change, which is harmless (a new version with an identical value).

   Confirm a new version landed:
   ```bash
   gcloud secrets versions list "$SECRET_NAME" --limit 2
   ```

5. **For `INTERNAL_API_KEY` only — coordinate the cutover.** The backend accepts exactly one key
   ([ADR 0005](../adr/0005-shared-secret-internal-api-key.md)), so there is no overlap window:
   the moment the new revision serves traffic, Apigee must already be sending the new key, or every
   consumer request returns `401`.

   Sequence, with someone on the Apigee side ready:
   1. Update the injected key in the Apigee target configuration and save, but **do not deploy the
      Apigee revision yet**.
   2. Run step 6 below and wait for the Cloud Run revision to be serving.
   3. Deploy the Apigee revision immediately.

   Expect a brief window — seconds to a minute — where consumer requests fail. Do this outside peak
   hours and tell consumers if the window matters.

6. **Redeploy so the new version is picked up.**
   ```bash
   ./deploy.sh
   ```
   See [runbook 01](01-deploy.md) for what this does and how to verify the deploy itself.

7. **Revoke the old credential** — only after verification below passes. Skipping this leaves a
   live credential in circulation and means the rotation achieved nothing.
   - OpenAI / Pinecone: delete the old key in the provider console.
   - `INTERNAL_API_KEY`: disable the superseded Secret Manager version:
     ```bash
     gcloud secrets versions disable VERSION_NUMBER --secret="$SECRET_NAME"
     ```

8. **Distribute the new `.env`** to anyone else who deploys, through a channel that is not email or
   chat. Their stale `.env` will otherwise overwrite your rotation the next time they run
   `setup-secrets.sh` — this is the most common way a rotation silently reverts.

## Verification

**`INTERNAL_API_KEY`** — the new key works and the old one does not:

```bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format='value(status.url)')"

curl -s -o /dev/null -w 'new key: %{http_code}\n' -X POST "$SERVICE_URL/commands/upsert-pinecone" \
  -H "x-api-key: NEW_KEY"
curl -s -o /dev/null -w 'old key: %{http_code}\n' -X POST "$SERVICE_URL/commands/upsert-pinecone" \
  -H "x-api-key: OLD_KEY"
```

Expected: `new key: 422` (authenticated, then missing form fields) and `old key: 401`.

Then confirm the full path through Apigee with a consumer key — the backend check above does not
exercise Apigee's injection.

**`OPENAI_API_KEY` / `PINECONE_API_KEY`** — only a real run proves these. Use a small CSV against a
scratch namespace ([runbook 04](04-run-udk-pipeline.md)) and confirm the job reaches
`status: completed`. A revoked or wrong key surfaces as an authentication error from the provider
partway through, after the job has already started.

## Rollback

Secret versions are retained, so reverting is re-pointing and redeploying:

```bash
gcloud secrets versions enable VERSION_NUMBER --secret="$SECRET_NAME"   # if disabled in step 7
```

Then restore the old value in `.env`, run `./setup-secrets.sh` (creating a new version with the old
value), and `./deploy.sh`.

**Do not roll back by routing traffic to the previous Cloud Run revision.** That revision is pinned
to whatever `:latest` resolved to when it was created, which makes the effective key ambiguous
during an incident. Roll the secret forward explicitly.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| All consumer requests `401` after rotation | Apigee still injecting the old key | Deploy the Apigee revision (step 5) |
| `500 INTERNAL_API_KEY not configured` | `.env` line was empty, so `setup-secrets.sh` skipped it with a warning | Check the script output, fix `.env`, repeat steps 4 and 6 |
| Rotation appears to revert days later | A colleague ran `setup-secrets.sh` from a stale `.env` | Step 8; consider whether `.env` should remain the source of truth |
| New value not taking effect | No redeploy after adding the version | `./deploy.sh` |
| `setup-secrets.sh` stored a mangled value | Quotes, inline `#` comments, or multi-line values in `.env` — the script parses with `grep`/`cut` | Store the raw value unquoted on one line |
