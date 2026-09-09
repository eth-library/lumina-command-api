# 03 — Bootstrap a GCP project

**Audience:** whoever stands up a new environment (staging, a replacement project, disaster recovery)
**When:** once per project, before the first deploy
**Duration:** 15–20 minutes

## Prerequisites

- `gcloud` installed and authenticated (`gcloud auth login`)
- Permission to create projects in the ETH organisation, or an already-created empty project
- A billing account to attach — Cloud Run, Cloud Build, and Secret Manager all require it
- Valid OpenAI and Pinecone API keys for the environment
- The repository cloned locally

## Variables

```bash
export PROJECT_ID="lumina-command-api-…"    # globally unique
export REGION="europe-west6"                # Zurich; matches deploy.sh
export BILLING_ACCOUNT="XXXXXX-XXXXXX-XXXXXX"
export ROUTER="lumina-egress-router"        # Cloud Router carrying the NAT gateway (step 8)
export NAT="lumina-command-api-nat"         # Cloud NAT gateway for the service's egress
```

## Steps

1. **Create the project and attach billing.** Skip the create if the project already exists.
   ```bash
   gcloud projects create "$PROJECT_ID"
   gcloud billing projects link "$PROJECT_ID" --billing-account "$BILLING_ACCOUNT"
   ```

2. **Set it as the active configuration.**
   ```bash
   gcloud config set project "$PROJECT_ID"
   gcloud config set run/region "$REGION"
   ```

3. **Enable the required APIs.** `cloudbuild` and `artifactregistry` are needed because
   `deploy.sh` builds from source ([ADR 0001](../adr/0001-fastapi-on-cloud-run.md)) — a deploy
   fails confusingly without them.
   ```bash
   gcloud services enable \
     run.googleapis.com \
     secretmanager.googleapis.com \
     cloudbuild.googleapis.com \
     artifactregistry.googleapis.com
   ```
   Enabling takes a minute or two to propagate.

4. **Grant the Cloud Run runtime service account access to secrets.** Without this the revision
   deploys and then fails to start, with nothing in the application logs to explain why.
   ```bash
   export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

   gcloud projects add-iam-policy-binding "$PROJECT_ID" \
     --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```
   This is the default compute service account. If the service is later deployed with a dedicated
   service account, grant the role to that one instead.

5. **Create the local `.env`.**
   ```bash
   cp .env.example .env
   ```
   Fill in `OPENAI_API_KEY`, `PINECONE_API_KEY`, and an `INTERNAL_API_KEY` you generate:
   ```bash
   openssl rand -base64 32
   ```
   Put each value raw and unquoted on one line — `setup-secrets.sh` parses with `grep`/`cut`.
   `.env` is gitignored and must never be committed.

6. **Upload the secrets.**
   ```bash
   ./setup-secrets.sh
   ```
   Expected: three `✅ … updated in Secret Manager` lines. A `⚠️ … skipping` line means that key was
   empty in `.env` — fix and re-run before continuing.

7. **First deploy.**
   ```bash
   ./deploy.sh
   ```
   See [runbook 01](01-deploy.md).

8. **Make sure the egress path can carry a burst.** `/pipeline/*` reaches the Lumina Engine's
   Prefect server through Direct VPC egress on `lumina-egress-vpc`, Cloud Router `$ROUTER`, and
   Cloud NAT `$NAT` with one static IP (`lumina-command-api-egress-ip`). **The creation of that
   VPC, router and gateway is not recorded here** — they were set up outside this runbook, and
   this step only verifies the one setting that has bitten: port allocation.

   Cloud NAT's default is static allocation, 64 ports per instance, each held 120 s after close.
   With the per-request client of [ADR 0007](../adr/0007-prefect-read-only-proxy.md) four page
   loads exhausted that and every further connection was refused
   ([ADR 0009](../adr/0009-shared-keepalive-client-for-prefect.md)). Dynamic allocation lifts the
   ceiling; the code fix keeps the service under it.
   ```bash
   gcloud compute routers nats describe "$NAT" --router "$ROUTER" --region "$REGION" \
     --format="yaml(enableDynamicPortAllocation,enableEndpointIndependentMapping,minPortsPerVm,maxPortsPerVm)"
   ```
   Expected: `enableDynamicPortAllocation: true`, `minPortsPerVm: 64`, `maxPortsPerVm: 4096`,
   `enableEndpointIndependentMapping: false`. If dynamic allocation is missing or `false`:
   ```bash
   gcloud compute routers nats update "$NAT" --router "$ROUTER" --region "$REGION" \
     --enable-dynamic-port-allocation --min-ports-per-vm 64 --max-ports-per-vm 4096
   ```
   Takes effect for new connections immediately; no redeploy. Dynamic allocation requires
   endpoint-independent mapping to be off — if it is on, add
   `--no-enable-endpoint-independent-mapping`, and `gcloud` refuses the update cleanly otherwise.
   Verified 2026-09-09: sixty uncached `/sources` calls in a row through Apigee, all `200`; before
   the change and the code fix, refusals began after four.

9. **Register the backend with Apigee X.** External consumers reach the API only through
   `api.library.ethz.ch` ([ADR 0004](../adr/0004-apigee-as-sole-public-ingress.md)). Apigee needs:
   - the Cloud Run service URL as the target endpoint,
   - the `INTERNAL_API_KEY` value to inject as `x-api-key` toward that target,
   - the OpenAPI document (fetch it from `$SERVICE_URL/openapi.json`),
   - CORS policy and the consumer-facing API product.

   This step is outside `gcloud` and needs Apigee access. Until it is done, the environment is
   reachable only by direct calls to the Cloud Run URL.

## Verification

```bash
export SERVICE_URL="$(gcloud run services describe lumina-command-api --region "$REGION" \
  --format='value(status.url)')"

curl -s "$SERVICE_URL/health"
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$SERVICE_URL/commands/upsert-pinecone"
```

Expected: `{"status":"ok",…}` and `401`.

Confirm the secrets are bound as references rather than literal values:

```bash
gcloud run services describe lumina-command-api --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env)"
```

Expected: three entries naming `secretKeyRef` sources. Literal values here mean a plain
`--set-env-vars` crept in — a violation of [ADR 0006](../adr/0006-secrets-in-secret-manager.md).

Then run a small end-to-end job ([runbook 04](04-run-udk-pipeline.md)) against a scratch Pinecone
namespace. Only that proves the OpenAI and Pinecone keys are valid.

## Rollback

Nothing here is destructive to an existing environment; it only adds. To dismantle a project
created in error:

```bash
gcloud projects delete "$PROJECT_ID"
```

Deletion is scheduled with a ~30-day recovery window. **Verify `PROJECT_ID` before running it** —
this is the one irreversible command in this directory.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PERMISSION_DENIED` enabling services | Billing not linked, or insufficient org rights | Step 1; check with `gcloud billing projects describe "$PROJECT_ID"` |
| Deploy fails with a Cloud Build error | `cloudbuild` / `artifactregistry` not enabled, or still propagating | Step 3; wait a minute and retry |
| Revision deploys, never becomes ready, no app logs | Step 4 skipped, or the service uses a non-default service account | Re-run step 4 for the account actually in use |
| `setup-secrets.sh` exits immediately | No `.env` in the working directory | Step 5; run from the repository root |
| Pinecone errors on the first real run | Index does not exist in this Pinecone project, or is in a different environment than `gcp-europe-west4` | Create the index; see [ADR 0003](../adr/0003-openai-embeddings-pinecone-index.md) |
