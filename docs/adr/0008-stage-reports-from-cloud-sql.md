# 0008 — Stage reports and the DAG from Cloud SQL, joined to Prefect by run id

**Status:** Proposed
**Date:** 2026-09-09
**Deciders:** Germano Giuliani, Jeremy Marbach (Lumina Engine)

> *Proposed, not yet built.* Written after the cross-team proposal *Stage reports and the DAG*
> (Studio side, 2026-09-09) and this repository's review of it. The four open questions at the
> end must be answered before implementation starts; the Decision section is written as if they
> resolve the way the review recommends, and will be corrected — before acceptance — if they do
> not.

## Context

[0007](0007-prefect-read-only-proxy.md) made this API a read-only façade over the Lumina Engine's
Prefect server: run state, timing and retries from Prefect, record counts read by regex out of
flow-run logs. That was the only structured-enough source available, and it works — with a known
weakness recorded in [spec 04](../specs/04-prefect-pipeline-status.md): a reworded log line
silently turns a figure into `null`, and a figure cannot be tied to the run that produced it,
because Prefect links nothing to nothing.

Two needs have now outgrown that:

- **Figures the Engine measures but does not log.** Lumina Studio needs to know how many
  Semantic Scholar records survive the abstract filter in `Merge: Sources`. No log line carries
  that count, and the only place the post-filter total appears is the *next* flow's log — which
  cannot be attributed to a specific unify run.
- **The DAG.** Which deployment waits for which lives only in the orchestrator's code. Studio
  carries a generated copy and has to notice by itself when it drifts.

The Engine will therefore write what it measures into Postgres: one row per flow run in
`lumina_pipeline.pipeline_stage_reports` (inputs, outputs, per-input kept/dropped counts), and one
row per orchestrator run in `lumina_pipeline.pipeline_dag`. Both live in a schema of their own on
the Cloud SQL instance that already hosts `lumina_core` and Studio's `lumina_studio`.

Someone has to read those tables and join them to Prefect. The cross-team proposal settles who:
this API. Studio keeps talking to exactly one system for pipeline state, and there is exactly one
place where Prefect's *state* and Postgres's *figures* are joined.

## Decision

We will give this API a **second, read-only data source**: the `lumina_pipeline` schema on
Cloud SQL, read with a dedicated Postgres role that can `SELECT` from that schema and nothing
else.

- **The join key is `flow_run_id`, and the join is by id — never "latest row per stage".** For
  every stage the API asks Prefect for the last run and then reads the report *of that run id*.
  If the last run crashed, the response says so and carries whatever the report holds; it does not
  quietly substitute the figures of an older successful run.
- **Log parsing stays as the fallback.** Where no report row exists for a run — stages the
  Engine has not migrated yet, or the short window before a row is written — the existing regex
  path answers, and `origin` on every figure says which path did: `stage-report` or
  `flow-run-log`.
- **The API translates; the tables speak Engine.** `pipeline_dag` rows carry `deployment`,
  `entrypoint` and `depends_on`. This API adds `stage` and `sources` from the mapping it already
  owns ([spec 04](../specs/04-prefect-pipeline-status.md)), so that mapping exists in one place.
- **Contract changes are additive.** `metrics` gains `origin`, `kept_records`, `dropped_records`,
  `reason` and `source_path`; `matched_line` becomes nullable (present, `null` for report-derived
  figures) rather than optional. `GET /pipeline/dag` is new. Nothing Studio reads today changes
  meaning, type or presence.
- **Plain Postgres, no vendor library.** One DSN from the environment (`PIPELINE_DATABASE_URI`,
  from Secret Manager), `asyncpg` with a small pool, TLS or the platform's Unix socket. On Cloud
  Run the socket is mounted with `--add-cloudsql-instances`; on any other platform the same
  variable points at a host. No IAM database authentication, no Cloud SQL connector — the same
  portability rule Studio follows.
- **A lifespan, deliberately.** [0007](0007-prefect-read-only-proxy.md) chose a client per
  request and no application lifespan. A connection pool needs one. This is a conscious departure,
  confined to the database; the Prefect client stays as it is.
- **Connection budget is explicit.** Pool `max_size` and Cloud Run `--max-instances` are set
  together so the product stays a small fraction of the instance's connection limit, which is
  shared with the Engine and Studio.

## Consequences

**Easier**

- Figures come from measurements, not from parsing prose. A reworded log line no longer costs a
  number.
- Every figure is tied to the run that produced it. "How many records reached Postgres last
  Sunday" has one answer.
- Studio deletes its generated DAG copy and reads the real one.
- The Engine can add a stage, and the API picks up its report with no regex to write.

**Harder**

- **A second availability dependency.** When Cloud SQL is unreachable, figures degrade to the log
  path (`origin: flow-run-log`) — the response stays 200. When Prefect is unreachable, `/pipeline/*`
  is 502 as before. The two failure modes are different and must stay distinguishable.
- **A second credential to rotate.** `PIPELINE_DATABASE_URI` joins `INTERNAL_API_KEY` in
  [runbook 02](../runbooks/02-rotate-secrets.md); the Postgres side of the rotation is the Engine's.
- **One more Apigee proxy.** `GET /pipeline/dag` is a new path, and Apigee proxies are per path
  ([runbook 05](../runbooks/05-apigee-proxy.md)). Without `lumina-pipeline-dag` the endpoint exists
  but no consumer can reach it.
- **Two paths for the same figure during the transition.** Until every stage writes reports, one
  response can mix `stage-report` and `flow-run-log` origins. That is why `origin` is on every
  figure rather than on the response.
- **Cloud SQL from Cloud Run needs IAM.** The service account needs `roles/cloudsql.client` on the
  instance's project — a binding on the deployment, not in the code, and one more thing
  [runbook 03](../runbooks/03-gcp-project-bootstrap.md) has to record.
- The report JSON is a contract owned by the Engine. `schema_version` lets this API notice a change;
  it does not let it survive one.

## Alternatives considered

**Studio reads the tables itself, through Payload** — Studio already sits on the same instance,
so a read costs nothing. Rejected because it would make Studio a second translator of Engine
vocabulary (`semscholar`, `entrypoint`, the Alma fold), because the join to Prefect's run state
would then happen in Studio, and because Studio's own rule is to derive nothing. The saving — one
database connection here — is smaller than the duplication it buys.

**A Payload collection in `lumina_studio`, written by the Engine, read by this API through Studio's
REST API** — rejected in the cross-team proposal: Payload would own a table it never validates, a
Studio migration could change columns the Engine writes, "latest report per stage" is not one query
in Payload's REST syntax, and this API would depend on Studio being up while Studio depends on
this API. One `GRANT` is cheaper.

**More log lines instead of tables** — the interim `Kept <key>: <n> rows` line is still worth
adding, because it fills the gap within one weekly run. As the long-term answer it is rejected for
the reasons the log path already has: brittle, unattributable, and every new figure is another
regex.

**Prefect artifacts** — recommended in [spec 04](../specs/04-prefect-pipeline-status.md) as the
durable fix. Not rejected on merit; superseded by the table, which additionally carries the DAG and
is readable with plain SQL by anyone the Engine grants access to.

**Latest completed report per stage, without the Prefect join** — one query, no id matching.
Rejected because it pairs the figures of the last *successful* run with the state of the last
*actual* run, and today those differ: `Merge: Sources` crashed on 2026-09-08, its last success is
2026-09-07. The response would show two runs as one.

## Open questions — to be answered before this ADR is accepted

1. **Which Cloud SQL instance?** Assumed: the one hosting `lumina_core` and `lumina_studio`, with
   a third schema `lumina_pipeline`. The Prefect metadata database is Prefect's property and was
   re-created once already; it is not a candidate.
2. **When does a report row become visible relative to Prefect's state change?** Assumed: the
   `INSERT` is the flow's last statement before it returns, so `COMPLETED` never precedes the row.
   If the Engine uses completion hooks instead, a short gap exists and the fallback covers it.
3. **Who carries `stage` and `sources` on DAG nodes?** Assumed and recommended: this API. If the
   orchestrator writes them anyway, this API ignores them in favour of its own mapping, so there is
   still one place — but the duplication should not exist.
4. **Report on failure?** Assumed: written when the inputs are known, with `state` saying how far
   the run got. "Never" is also clean; "sometimes, unmarked" is not.
