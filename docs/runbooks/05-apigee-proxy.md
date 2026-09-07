# 05 — Publish an endpoint through Apigee X

**Audience:** anyone with `roles/apigee.apiAdminV2` on the Apigee organisation
**When:** a new backend path prefix has been deployed and consumers need to reach it; or an
existing proxy's target, key, or documentation changes
**Duration:** 15–30 minutes for a new proxy
**Last verified:** 2026-09-07 — proxy bundles built and validated; upload and deployment steps
follow the four existing `/commands` proxies and the Apigee X documentation, and have not yet been
executed end to end as written

A deploy to Cloud Run succeeds whether or not Apigee knows about the new endpoints, and they answer
on the Cloud Run URL either way. The gap is invisible from the backend side and shows up only for
consumers, who reach the service exclusively through `api.library.ethz.ch`
([ADR 0004](../adr/0004-apigee-as-sole-public-ingress.md)).

## Prerequisites

- The backend revision is deployed and verified ([runbook 01](01-deploy.md))
- `gcloud` authenticated against the Apigee organisation — `gcloud auth list`
- `apigeecli` on the `PATH` — `apigeecli -v`. Every step also has a UI equivalent; the UI is
  authoritative if the two disagree.
- The proxy bundle exists. For `/pipeline/*` these are `lumina-pipeline-sources` and
  `lumina-pipeline-runs`; their structure is described under *Anatomy of a proxy* below.

## Variables

```bash
export APIGEE_ORG="…"                 # Apigee X organisation
export APIGEE_ENV="default-prod"      # environment the existing proxies are deployed to
export SERVICE="lumina-command-api"
export REGION="europe-west6"
export TOKEN="$(gcloud auth print-access-token)"
export APIGEE_BASE="https://api.library.ethz.ch/lumina/v1"
```

`TOKEN` expires after roughly an hour. Re-run that line when a command returns `401`.

## Steps

1. **Confirm the backend target URL.** The proxy hardcodes it, so a wrong value fails at runtime
   rather than at upload.
   ```bash
   gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'
   ```
   Cloud Run serves the same revision under more than one hostname. The existing proxies use the
   project-number form (`lumina-command-api-171616207524.europe-west6.run.app`); keep to it so all
   proxies name the same host.

2. **Set the backend key in the bundle.** `AM-InjectBackendApiKey` carries `INTERNAL_API_KEY` as a
   literal — the mechanism the four `/commands` proxies already use.
   ```bash
   gcloud secrets versions access latest --secret=INTERNAL_API_KEY
   ```
   Paste the value into `apiproxy/policies/AM-InjectBackendApiKey.xml`, replacing the placeholder.

   **This is the mechanism's weak point.** Each proxy holds its own copy, so the key now exists in
   as many places as there are proxies, and [runbook 02](02-rotate-secrets.md) has to update every
   one of them in the same window. Moving all proxies to a single encrypted KVM would reduce this
   to one place; that is a change to the shared convention and needs its own decision, not an
   ad-hoc departure in one proxy.

3. **Upload the bundle and deploy it.**
   ```bash
   for P in lumina-pipeline-sources lumina-pipeline-runs; do
     apigeecli apis create bundle -o "$APIGEE_ORG" -n "$P" -p "./$P/apiproxy" -t "$TOKEN"
     apigeecli apis deploy -o "$APIGEE_ORG" -e "$APIGEE_ENV" -n "$P" -v 1 --ovr -t "$TOKEN"
   done
   ```
   In the UI: *Proxy development → API proxies → Create → Upload proxy bundle*, then **Deploy** to
   the environment.

4. **Add the proxy to an API product.** Until this is done `VA-VerifyAPIKey` rejects every request,
   because a consumer key grants access to products, not to proxies. Adding the new proxies to the
   existing Lumina product makes every current consumer key work immediately; a separate product
   gives Lumina Studio its own quota and revocation.

   UI: *Distribution → API products*.

5. **Publish the documentation.** The OpenAPI documents live in
   [`docs/openapi/`](../openapi/) — one per proxy, describing the gateway view.

   UI: *Publish → Portals → \<portal\> → API catalog → Add API*, select the proxy, upload the
   matching YAML, and assign it to the API product from step 4.

## Verification

```bash
export CK="…"                          # a consumer key from the API product

echo "--- ohne Key: 401 ---"
curl -s -o /dev/null -w '%{http_code}\n' "$APIGEE_BASE/pipeline/sources"

echo "--- mit Key: 200 ---"
curl -s -o /dev/null -w '%{http_code}\n' "$APIGEE_BASE/pipeline/sources" -H "x-api-key: $CK"

echo "--- Pfadrest wird durchgereicht: 200 ---"
curl -s -o /dev/null -w '%{http_code}\n' "$APIGEE_BASE/pipeline/sources/erara" -H "x-api-key: $CK"

echo "--- unbekannte Quelle, 404 vom Backend ---"
curl -s "$APIGEE_BASE/pipeline/sources/gibtsnicht" -H "x-api-key: $CK"

echo "--- zweiter Proxy: 200 ---"
curl -s -o /dev/null -w '%{http_code}\n' "$APIGEE_BASE/pipeline/runs?state=RUNNING" -H "x-api-key: $CK"

echo "--- CORS-Preflight, ohne Backend-Kontakt ---"
curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS "$APIGEE_BASE/pipeline/sources" \
  -H "Origin: https://example.ethz.ch"

echo "--- Response-Cache: der zweite Aufruf ist deutlich schneller ---"
curl -s -o /dev/null -w 'kalt %{time_total}s\n' "$APIGEE_BASE/pipeline/sources" -H "x-api-key: $CK"
curl -s -o /dev/null -w 'warm %{time_total}s\n' "$APIGEE_BASE/pipeline/sources" -H "x-api-key: $CK"
```

Two of these deserve attention rather than a glance:

- **The path suffix.** `/sources/erara` must arrive at the backend as `/pipeline/sources/erara`.
  A `404` carrying `Unknown source 'erara'` means Apigee dropped the suffix — check the target URL.
- **The cache.** If the warm call is no faster, `RC-PipelineCache` is not taking effect. The usual
  cause is `response.streaming.enabled` being set on the proxy or target: Apigee cannot cache a
  streamed response, and it fails silently. The `/commands` proxies set it deliberately for large
  uploads; these two must not.

## Rollback

Undeploying leaves the proxy in place but removes it from traffic; consumers get `404` from
Apigee immediately.

```bash
apigeecli apis undeploy -o "$APIGEE_ORG" -e "$APIGEE_ENV" -n lumina-pipeline-sources -v 1 -t "$TOKEN"
```

To go back to an earlier revision of a proxy that already worked, deploy that revision number
instead of undeploying — Apigee keeps every uploaded revision.

```bash
apigeecli apis listdeploy -o "$APIGEE_ORG" -n lumina-pipeline-sources -t "$TOKEN"
apigeecli apis deploy -o "$APIGEE_ORG" -e "$APIGEE_ENV" -n lumina-pipeline-sources -v 1 --ovr -t "$TOKEN"
```

Removing a proxy from an API product takes effect for all consumers of that product at once.
There is no per-consumer rollback.

## Anatomy of a proxy

All six Lumina proxies share one shape: **one proxy per endpoint**, the full path in the basepath,
and therefore no conditional flows.

| Element | Purpose |
|---------|---------|
| `VA-VerifyAPIKey` | Checks the consumer key. Skipped for `OPTIONS`, which carries no key. |
| `AM-CORSPreflight` | Answers the preflight in the proxy. Paired with `RouteRule name="NoRoute"`, so a preflight never reaches Cloud Run. |
| `AM-CORSHeaders` | Adds the CORS header to the response — and, via `DefaultFaultRule`, to error responses too. Without that, a browser sees a CORS error instead of the real `401` or `502`. |
| `AM-InjectBackendApiKey` | Replaces the consumer key with the internal one. Sits in the **target** PreFlow. |
| `RC-PipelineCache` | `/pipeline/*` only. 60 s, keyed on path suffix and query string, skipped for responses from 400 upward. |

`BasePath` follows `/lumina/v1/<backend path>`, and the target URL is the Cloud Run host plus the
same backend path. A request's path suffix is appended to the target URL, which is how one proxy
serves both `/sources` and `/sources/{source_id}`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401` even with a valid consumer key | The proxy is in no API product | Step 4 |
| `401` with `{"detail":"Invalid API key."}` | The response comes from the **backend**: the literal in `AM-InjectBackendApiKey` does not match `INTERNAL_API_KEY` | Step 2; check whether a rotation ([02](02-rotate-secrets.md)) missed this proxy |
| `404` from Apigee, not from the backend | Basepath does not match, or the proxy is not deployed to this environment | `apigeecli apis listdeploy` |
| `404` from the backend with `Unknown source` | The target URL lost the path suffix | Step 1 |
| Browser reports a CORS error on a failed request | `DefaultFaultRule` is missing `AM-CORSHeaders` | Compare against an existing proxy |
| Cache never hits | `response.streaming.enabled` is set | Remove it from proxy and target |
| `502` on `/pipeline/*` only | Cloud Run cannot reach the Prefect server of the Lumina Engine | Not an Apigee problem — [runbook 01](01-deploy.md), step 4, and [ADR 0007](../adr/0007-prefect-read-only-proxy.md) |
| Portal shows no "Try it" console | The OpenAPI document is not assigned to the API product | Step 5 |
