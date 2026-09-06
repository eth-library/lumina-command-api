# 01 — Deploy to Cloud Run

**Audience:** any team member with `roles/run.developer` on the project
**When:** shipping a change to `main`; applying a rotated secret ([02](02-rotate-secrets.md))
**Duration:** 3–6 minutes (source build dominates)

## Prerequisites

- `gcloud` installed and authenticated — check with `gcloud auth list`
- The project has been bootstrapped ([03](03-gcp-project-bootstrap.md)); all three secrets exist
- Working directory is the repository root (the deploy uploads `.` as build context)
- The change you intend to ship is committed — the build uses the **working directory**, not the
  git HEAD, so uncommitted edits deploy silently

## Variables

```bash
export PROJECT_ID="$(gcloud config get-value project)"
export SERVICE="lumina-command-api"
export REGION="europe-west6"
export API_KEY="…"          # INTERNAL_API_KEY, for the smoke test in Verification
```

## Steps

1. **Confirm you are pointed at the right project.** `deploy.sh` passes `--region` explicitly but
   takes the project from your active configuration, and deploying to the wrong one is the most
   expensive mistake in this runbook.
   ```bash
   gcloud config get-value project
   ```
   Expected: your intended `PROJECT_ID`.

2. **Confirm the secrets the revision will bind to exist.**
   ```bash
   gcloud secrets list --filter="name~(OPENAI|PINECONE|INTERNAL)_API_KEY" --format="value(name)"
   ```
   Expected: all three names. A missing secret produces a revision that fails to start.

3. **Note the current revision**, so rollback does not require guesswork later.
   ```bash
   gcloud run services describe "$SERVICE" --region "$REGION" \
     --format="value(status.traffic[0].revisionName)"
   ```
   Write the output down. This is your rollback target.

4. **Deploy.**
   ```bash
   ./deploy.sh
   ```
   This runs `gcloud run deploy --source .`: Buildpacks builds the image, pushes it, creates a new
   revision with 8 GiB / 4 vCPU / 3600 s timeout, binds the three secrets at `:latest`, sets
   `PREFECT_API_URL` as a plain environment variable, and routes 100 % of traffic to it.

   Expected tail: `Service [lumina-command-api] revision [...] has been deployed and is serving
   100 percent of traffic.`

## Verification

1. **Service responds and reports the expected environment:**
   ```bash
   export SERVICE_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" \
     --format='value(status.url)')"
   curl -s "$SERVICE_URL/health"
   curl -s "$SERVICE_URL/version"
   ```
   Expected: `{"status":"ok","env":...}` and the version you expect to be serving.

2. **Auth is wired** — a request with no key must be rejected:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -X POST "$SERVICE_URL/commands/upsert-pinecone"
   ```
   Expected: `401`. A `500` means `INTERNAL_API_KEY` did not reach the container — check the
   secret binding before going further. A `422` means the auth dependency is not applied.

3. **The key that Apigee will send is the key the service expects:**
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -X POST "$SERVICE_URL/commands/upsert-pinecone" \
     -H "x-api-key: $API_KEY"
   ```
   Expected: `422` (authenticated, then rejected for missing form fields — which is the pass
   condition here). `401` means the deployed key differs from `$API_KEY`.

4. **The Prefect façade can reach the Engine** — this is the one check that exercises a network
   path Cloud Run does not otherwise use ([ADR 0007](../adr/0007-prefect-read-only-proxy.md)):
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' "$SERVICE_URL/pipeline/sources" \
     -H "x-api-key: $API_KEY"
   ```
   Expected: `200`. A `502` means the revision cannot reach `lumina-box01.ethz.ch:4200` — the
   backend is otherwise healthy, so the rest of the API keeps working; see Troubleshooting.

5. **No startup errors in the logs:**
   ```bash
   gcloud run services logs read "$SERVICE" --region "$REGION" --limit 50
   ```

6. **End-to-end through Apigee**, if the change touches the request or response contract — a
   backend that passes every check above can still be broken for real consumers, because they
   arrive through `api.library.ethz.ch` with a different key and a CORS preflight
   (see [ADR 0004](../adr/0004-apigee-as-sole-public-ingress.md)).

## Rollback

Cloud Run keeps previous revisions. Rolling back is a traffic change, not a rebuild, and takes
seconds.

```bash
gcloud run revisions list --service "$SERVICE" --region "$REGION" --limit 5

gcloud run services update-traffic "$SERVICE" --region "$REGION" \
  --to-revisions "REVISION_NAME_FROM_STEP_3=100"
```

Verify with the health and version checks above.

**Caveat:** rolling back the revision does **not** roll back a secret version. If this deploy was
applying a rotated key, see [02](02-rotate-secrets.md) — the old revision is pinned to the secret
version that was `:latest` when *it* was created, so a rollback may resurrect the previous key.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Revision fails to start, no application logs | Runtime service account lacks `secretmanager.secretAccessor`, or a bound secret does not exist | [Runbook 03](03-gcp-project-bootstrap.md), step 4 |
| `500 INTERNAL_API_KEY not configured` | Secret bound but empty, or `--set-secrets` missing from `deploy.sh` | Re-run [02](02-rotate-secrets.md); confirm the flag in `deploy.sh` |
| Build fails resolving dependencies | `requirements.txt` pin unavailable, or buildpack picked a Python version a dependency does not support | Read the Cloud Build log URL printed by the deploy |
| Deploy succeeds but serves old behaviour | Uncommitted or unsaved files; `--source .` uploads the working directory | `git status`, then redeploy |
| `413` or a truncated upload from a client | Cloud Run's ~32 MB request cap ([ADR 0001](../adr/0001-fastapi-on-cloud-run.md)) | Client must gzip the payload |
| `502` from `/pipeline/*` only | Cloud Run cannot reach `lumina-box01.ethz.ch:4200`, or Prefect is down there | Check the Engine host first; if the host is up but unreachable from Cloud Run, the network path needs a decision of its own ([ADR 0007](../adr/0007-prefect-read-only-proxy.md)) |
| `/pipeline/sources` returns `"records": null` everywhere | A log message was reworded in `lumina-engine`, so no pattern matches | Compare the flow-run log against the patterns in [spec 04](../specs/04-prefect-pipeline-status.md) |
