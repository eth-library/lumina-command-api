# OpenAPI documents

The API contract **as consumers see it** — through Apigee X at `api.library.ethz.ch`, with a
consumer key. One document per Apigee proxy, uploaded to the developer portal's API catalog by
[runbook 05](../runbooks/05-apigee-proxy.md).

| Document | Apigee proxy | Backend |
|----------|--------------|---------|
| [`lumina-pipeline-sources.yaml`](lumina-pipeline-sources.yaml) | `lumina-pipeline-sources` | `GET /pipeline/sources`, `GET /pipeline/sources/{source_id}` |
| [`lumina-pipeline-runs.yaml`](lumina-pipeline-runs.yaml) | `lumina-pipeline-runs` | `GET /pipeline/runs` |

## What these are, and what they are not

They are **derived** — the code is the source of truth, and FastAPI generates its own OpenAPI
document at `/openapi.json` describing the backend. These describe something that document cannot:
the gateway-facing view. Different server URL, a consumer key instead of the internal one, and the
response cache's effect on freshness.

They are also the **only version-controlled API contract this repository has**.
[ADR 0004](../adr/0004-apigee-as-sole-public-ingress.md) records the gap they partly close: the
contract lives both in FastAPI's generated document and in Apigee, the two drift silently, and the
`openapi.json` the README refers to has never existed. These files close that gap for
`/pipeline/*` only. `/commands/*` remains undocumented here.

Being version-controlled does not make them authoritative. When they disagree with the code, the
code is right and the document is stale.

## Rules

- **Written in English**, unlike [`endpoints/`](../endpoints/), which is German for its Confluence
  audience. These are the machine-readable contract in a developer portal: they are read by people
  outside the ETH Library, and by tooling that generates clients from them.
- **One document per Apigee proxy**, named after it. A portal entry maps to a proxy, not to a
  backend namespace.
- **They describe the gateway, not the backend.** `servers` is `api.library.ethz.ch`, and the
  security scheme is the consumer key. The internal key never appears — not as a value, not as a
  scheme.
- **Update them in the same commit as a contract change.** A new field, a renamed field, a new
  status code, a changed default: all of it belongs here before the portal is refreshed.
- **Verify against a running instance rather than by reading.** The check that matters compares
  every declared schema with a real response in both directions — fields the response carries but
  the schema omits, and required fields the response does not deliver. Both documents were
  validated that way on 2026-09-07 against `/sources`, three source details, and 30 runs.
- Documented behaviour includes the awkward parts: that record counts come from log lines, that
  `null` never means zero, that scheduled runs sort first. A portal that only lists field names
  sends people to read the source.

## Verifying a change

With the service running locally and the documents edited, compare them against real responses.
The [spec](../specs/04-prefect-pipeline-status.md) states what the endpoints must return; this
checks that the documents say the same thing.

```bash
source .venv/Scripts/activate
uvicorn app.main:app --port 8080 &

curl -sS localhost:8080/pipeline/sources -H "x-api-key: $INTERNAL_API_KEY" | python -m json.tool
```

Read the response beside the document. Every key present must be declared; every `required` key
declared must be present; every `null` must sit under a `nullable: true`; every observed enum
value must be listed.
