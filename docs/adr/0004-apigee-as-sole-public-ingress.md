# 0004 — Apigee X as the sole public entry point

**Status:** Accepted
**Date:** 2026-04-22
**Deciders:** Germano Giuliani

> *Retroactive record.* Implemented 2026-04-22 (`feat: Add API key authentication to commands
> router…` and the architecture section of the README); written 2026-07-31. Context and
> alternatives are reconstructed.

## Context

ETH Library publishes its APIs through **Apigee X** at `api.library.ethz.ch`. That is where
consumers are registered, where API products and quotas are defined, and where the library's API
governance lives. A service that published its own endpoint would sit outside all of it.

The consumers of this API are other applications and staff tools, some browser-based, which means
CORS has to be handled somewhere. Consumers also need credentials that can be issued and revoked per
consumer, without redeploying the backend.

Meanwhile the Cloud Run service has a URL of its own the moment it is deployed
([0001](0001-fastapi-on-cloud-run.md)), and that URL is reachable from the internet.

## Decision

We will treat **Apigee X as the only supported way to reach this API**. The Cloud Run URL is an
implementation detail and is not published to consumers.

The request path is:

```
Client  ──x-api-key: <consumer key>──▶  Apigee X (api.library.ethz.ch)
                                          • verifies the consumer key
                                          • applies CORS
                                          • replaces the header with the internal key
                                       ──x-api-key: <internal key>──▶  Cloud Run
```

- **Apigee owns consumer identity.** Keys are issued, scoped, and revoked there.
- **Apigee owns CORS.** The FastAPI application deliberately registers no CORS middleware.
- **Apigee injects the internal key** ([0005](0005-shared-secret-internal-api-key.md)) so consumers
  never see or hold it.
- The Cloud Run service stays `--allow-unauthenticated` at the platform level and enforces the
  internal key in application code.
- The OpenAPI document that FastAPI generates is the contract Apigee is configured against.

## Consequences

**Easier**

- One place to add a consumer, set a quota, revoke access, or read usage analytics — no code change
  and no deploy.
- CORS policy is managed centrally and consistently with the library's other APIs.
- The backend stays simple: one header check, no consumer registry, no token verification.
- The Cloud Run revision can be replaced or the region changed without consumers noticing.

**Harder**

- **The Cloud Run URL remains publicly reachable and bypasses every Apigee control.** Anyone who
  knows the URL and the internal key gets unmetered, unlogged, un-quota'd access to the pipeline —
  and to the OpenAI spend behind it. Apigee is a front door, not a wall; the only thing enforcing
  the front door is a shared secret. Mitigations available if this becomes unacceptable: Cloud Run
  IAM with a service-account token from Apigee, or ingress restricted to internal + Cloud Load
  Balancing.
- **The API contract lives in two places.** FastAPI generates the OpenAPI document; Apigee is
  configured from a copy of it. They drift silently — an endpoint added here is invisible to
  consumers until Apigee is updated. The README references a committed `openapi.json` for this
  purpose, **but no such file exists in the repository**, so the Apigee-side contract currently has
  no version-controlled source.
- **Two credential layers must be rotated in step.** See
  [runbook 02](../runbooks/02-rotate-secrets.md).
- Local development and Postman testing hit the backend directly with the internal key, so they
  exercise a path that no production consumer uses — CORS and quota bugs cannot surface in testing.
- Apigee is now an availability dependency: if it is down, the API is down for everyone, even though
  the backend is healthy.

## Alternatives considered

**Cloud Run IAM (`--no-allow-unauthenticated`) with Apigee calling as a service account** — closes
the bypass completely: the backend becomes unreachable without a Google-signed token, and the shared
secret stops being the only defence. Rejected for the initial rollout as extra moving parts in the
Apigee target configuration. **This is the recommended path if the service ever handles non-public
data**, and it composes with, rather than replaces, the current design.

**Google Cloud API Gateway** — lighter and cheaper than Apigee, natively integrated with Cloud Run.
Rejected because it is not where ETH Library's API governance, consumer registry, or developer
portal live. Being consistent with the institution outweighs the simplicity.

**Publishing the Cloud Run URL directly** — no gateway at all. Rejected: no per-consumer keys, no
quota, no analytics, CORS to implement in application code, and the published endpoint would be tied
to a Cloud Run revision URL forever.
