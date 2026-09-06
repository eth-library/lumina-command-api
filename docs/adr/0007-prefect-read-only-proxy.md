# 0007 — A read-only façade over the Lumina Engine's Prefect server

**Status:** Accepted
**Date:** 2026-09-06
**Deciders:** Germano Giuliani

## Context

The Lumina Engine orchestrates its harvesting, parsing and deduplication pipeline with Prefect 3,
running on `lumina-box01.ethz.ch:4200`. Lumina Studio needs to show two things: what the six data
sources are and how they are doing, and what the pipeline has been running.

Prefect already holds that information and exposes a REST API for it. Studio could call it directly.
Four facts argue against that:

- **The Prefect API is unauthenticated.** Anyone who can reach the host can read it — and equally
  can trigger runs, pause deployments, or delete them. Its write surface is as open as its read
  surface.
- **It is an ETH-internal host.** A browser application published through
  `api.library.ethz.ch` cannot reach it, and giving Studio a second, differently-networked backend
  splits its deployment story in two.
- **It speaks Prefect, not Lumina.** It knows `flows`, `deployments` and `flow_runs`. It has no
  concept of a *data source*. Turning 19 deployments into 6 sources is domain knowledge that would
  otherwise be duplicated into every consumer that wants it.
- **What Studio needs is not in structured form.** This server stores zero artifacts and zero task
  runs. The record counts per source exist only as free text inside flow-run logs. Somebody has to
  parse them, and that should happen once, not in each client.

Meanwhile `lumina-command-api` already sits behind Apigee X with a shared-secret key
([0004](0004-apigee-as-sole-public-ingress.md), [0005](0005-shared-secret-internal-api-key.md)) and
is already the place where Lumina-domain logic lives.

Its existing surface, however, is `/commands/*`: write operations that start long-running jobs. A
status query is neither a command nor long-running, and this codebase has so far had exactly one
router, no HTTP client of its own, and no outbound integration that was not a vendor SDK.

## Decision

We will add a **read-only façade** over the Prefect API to `lumina-command-api`, under a new
`/pipeline/*` namespace.

- **Read-only is a property of the design, not a convention.** The service issues only `GET`
  requests and `POST` to Prefect's `.../filter` and `.../count` paths — the read verbs of Prefect's
  API. It has no code path that can create, modify, delete, or trigger anything in Prefect. The
  spec makes this a testable acceptance criterion.
- **A new router, not an extension of `/commands`.** `/commands/*` means "do something"; these
  endpoints mean "tell me something". Mixing them would make the namespace meaningless.
- **The same authentication as `/commands/*`.** The same `x-api-key` header, the same
  `INTERNAL_API_KEY` secret, the same `verify_api_key` dependency — no second credential, no second
  mechanism. Because that dependency is attached to the router rather than to individual routes
  ([0005](0005-shared-secret-internal-api-key.md)), the new router declares it explicitly:
  `APIRouter(prefix="/pipeline", dependencies=[Depends(verify_api_key)])`.
- **`httpx` becomes a declared dependency.** This is the first raw HTTP client in the codebase. A
  client is created per request with a 10-second timeout; there is no shared client and no
  application lifespan.
- **The service layer is `async` here.** Existing services in `app/services/` are synchronous and
  bridged with `asyncio.to_thread`, which suits CPU-bound pipeline work. This one is pure I/O
  fan-out — roughly 13 parallel Prefect calls per request — so it is `async def` and the router
  awaits it directly.
- **No caching in this API.** Every request queries Prefect afresh. Response caching, if it is ever
  needed, is configured in Apigee, which can do it on the path without the backend emitting a
  `Cache-Control` header.
- **The Prefect base URL is configuration, not a secret**: `PREFECT_API_URL`, set with
  `--set-env-vars`, defaulting to `http://lumina-box01.ethz.ch:4200/api`. There is no credential to
  protect, because Prefect has none.

## Consequences

**Easier**

- Studio makes one authenticated call against the backend it already talks to, and gets Lumina
  domain objects instead of Prefect internals.
- The mapping from deployments to sources, and the log parsing behind the record counts, live in
  one reviewed place instead of in every consumer.
- Prefect's open write surface is never exposed. The façade cannot pass a write through, because it
  contains no code that writes.
- Apigee's existing consumer keys, quotas and analytics apply to the new endpoints for free.

**Harder**

- **Prefect becomes an availability dependency of this API.** When it is down or the network path
  fails, `/pipeline/*` returns 502 while the rest of the service is healthy. Studio must render a
  degraded state rather than assume the data is always there.
- **The record counts rest on log parsing and will break silently.** A reworded log line in
  `lumina-engine` turns a number into `null` with no error anywhere. We chose a missing number over
  a wrong one, but the coupling is real and invisible from this repository. The durable fix is for
  `lumina-engine` to publish these counts as Prefect artifacts; until then this is technical debt
  we are knowingly taking on.
- **Cloud Run must be able to reach an ETH-internal host.** The endpoints were developed and
  verified from inside the ETH network, which said nothing about a Cloud Run revision. The first
  deploy was therefore also the test: step 4 of [runbook 01](../runbooks/01-deploy.md) calls
  `/pipeline/sources` against the deployed service. Had it returned 502, the decision to host the
  façade on Cloud Run would have had to be revisited — a VPC connector or an internally-hosted
  deployment, each warranting its own ADR. The blast radius of being wrong was contained: only
  `/pipeline/*` fails, the rest of the API is unaffected.

  > **Resolved 2026-09-06.** The first deploy to `ethbib-lumina` answered `200` in 0.55 s from
  > `europe-west6`, with no VPC connector and no ingress change. The risk above did not
  > materialise. It stays on record because nothing guarantees the path: it is not a configured,
  > documented route but an incidental one, and a firewall or network change on either side would
  > break `/pipeline/*` without warning. Runbook 01 step 4 remains the check on every deploy.
- **Apigee must be configured for `/pipeline/*` separately.** Until it is, the endpoints exist but
  no consumer can reach them. This is the drift that [0004](0004-apigee-as-sole-public-ingress.md)
  already records: the contract lives both in FastAPI's generated OpenAPI document and in Apigee.
- **Two service styles now coexist** in `app/services/` — synchronous pipeline services and one
  async I/O service. A reader has to notice which kind they are looking at.
- The six-source mapping is a hardcoded table. A seventh source added to `lumina-engine` will not
  appear in Studio until this repository is changed.

## Alternatives considered

**Studio calls Prefect directly** — no new code here at all. Rejected on four counts: Studio would
need network access to an ETH-internal host it otherwise does not touch; the unauthenticated write
surface would be one URL away from a browser application; every consumer would reimplement the
deployment-to-source mapping; and the record counts would have to be scraped out of log text in the
frontend.

**New endpoints under `/commands/*`** — no new router, no namespace decision. Rejected because
`/commands` denotes write operations that start jobs. A `GET /commands/pipeline-status` would
mislead every future reader about what the namespace means.

**Cache the Prefect responses in this service** — fewer calls to an on-prem box. Rejected because
Cloud Run runs several ephemeral instances, so an in-process cache is per-instance and gives
inconsistent answers across requests ([0001](0001-fastapi-on-cloud-run.md) already records this for
the polling job store). Apigee is the correct layer, and it needs nothing from us.

**Have `lumina-engine` push status into a store this API reads** — no runtime coupling to Prefect,
no 502s, and a natural home for structured counts. Rejected for now as disproportionate: it needs a
new datastore, a writer in a repository we do not own, and a schema contract between the two. Worth
revisiting if Prefect's availability turns out to be a problem, and it composes well with the
artifacts recommendation above.

**A separate API key for `/pipeline/*`** — read access could then be granted without granting
`/commands` access. Rejected because per-consumer scoping is exactly what Apigee's API products
already provide ([0004](0004-apigee-as-sole-public-ingress.md)); a second backend secret would add
a rotation burden ([runbook 02](../runbooks/02-rotate-secrets.md)) to solve a problem one layer up
has already solved.
