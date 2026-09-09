# Architecture Decision Records

**This index is the source of truth for ADR status.** If a document's header and this table
disagree, the table wins — fix the document.

| # | Title | Status | Date |
|---|-------|--------|------|
| [0001](0001-fastapi-on-cloud-run.md) | FastAPI on Cloud Run, deployed from source with Buildpacks | Accepted | 2026-02-23 |
| [0002](0002-numbered-step-modules-pipeline.md) | Numbered step modules as the transformation pipeline convention | Accepted | 2026-03-25 |
| [0003](0003-openai-embeddings-pinecone-index.md) | OpenAI embeddings with a Pinecone vector index | Accepted | 2026-04-20 |
| [0004](0004-apigee-as-sole-public-ingress.md) | Apigee X as the sole public entry point | Accepted | 2026-04-22 |
| [0005](0005-shared-secret-internal-api-key.md) | Shared-secret internal API key for `/commands/*` | Accepted | 2026-04-22 |
| [0006](0006-secrets-in-secret-manager.md) | Secrets in Secret Manager, injected as env vars at deploy time | Accepted | 2026-04-22 |
| [0007](0007-prefect-read-only-proxy.md) | A read-only façade over the Lumina Engine's Prefect server | Accepted | 2026-09-06 |
| [0008](0008-stage-reports-from-cloud-sql.md) | Stage reports and the DAG from Cloud SQL, joined to Prefect by run id | Proposed | 2026-09-09 |
| [0009](0009-shared-keepalive-client-for-prefect.md) | One shared keep-alive client for Prefect reads (amends 0007) | Accepted | 2026-09-09 |

Next number: **0010**.

## When to write one

Write an ADR **before** the decision is implemented when you:

- adopt or replace a framework, runtime, hosting platform, or database
- change how auth, authorization, or secrets work
- add an external integration that crosses a trust boundary
- establish a cross-module convention
- reverse a previous ADR

Not needed for routine feature work, minor dependency upgrades, or refactors that keep public
contracts intact.

## Rules

- Numbers are assigned monotonically and **never reused**, even if an ADR is abandoned.
- Filenames are `NNNN-kebab-case-title.md`.
- Copy [`TEMPLATE.md`](TEMPLATE.md) to start.
- **Superseding:** write a *new* ADR that references its predecessor, then set the predecessor's
  status to `Superseded by NNNN` here and in its header. **Never edit an accepted ADR's Decision
  section** — it records what we believed at the time, and rewriting it destroys the only reason
  the record exists.
- Correcting a typo, a broken link, or a factual error in Context is fine. Changing what the
  decision *was* is not.

## About 0001–0006

These were written retroactively on 2026-07-31 to establish a baseline for a system that was built
before this convention existed. Each is dated to when the decision actually landed in `main`, and
each carries a note saying so.

Their **Decision** sections are reliable — they were reconstructed from the code, `deploy.sh`, and
`setup-secrets.sh`, and describe what the system verifiably does. Their **Context** and
**Alternatives considered** sections are inference. Where they misstate the reasoning, correct
them; an ADR that records the wrong *why* is worse than none.

The next ADR written for this project should be a real one, written before its decision is built.
