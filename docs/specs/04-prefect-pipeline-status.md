# 04 — Prefect pipeline status

**Status:** Implemented
**Date:** 2026-09-06
**Author:** Germano Giuliani

## Goal

Lumina Studio can show two dashboard sections — one describing the six data sources of the Lumina
Engine, one showing the state of its pipeline runs — without talking to the Prefect server itself
and without anyone hand-maintaining a list of what the Engine ingests.

## User stories

- As a **Lumina Studio developer**, I want one authenticated call that returns all six sources with
  their description, pipeline stages, and record counts, so that I can render the sources section
  without hardcoding source names or knowing anything about Prefect.
- As a **library staff member using Studio**, I want to see when each source was last processed and
  how many records it contributed, so that I can tell whether the catalogue behind Lumina is current.
- As a **library staff member using Studio**, I want to see which pipeline runs are running, failed,
  or scheduled, so that I notice a stuck or broken run without opening the Prefect UI.
- As an **operator of this API**, I want a Prefect outage to surface as an explicit `502` rather
  than a hanging request, so that Studio can show "status unavailable" instead of spinning.

## Acceptance criteria

- [ ] Given a reachable Prefect server, when `GET /pipeline/sources` is called, then exactly six
      sources are returned: `slsp_eth`, `slsp_network`, `epics`, `erara`, `research_collection`,
      `semantic_scholar`.
- [ ] Given a stage whose deployment has never run, then that stage is returned with
      `"last_run": null` and HTTP **200**, not 404 and not 500. This is a normal state, not an
      error: on 2026-09-05 all six harvesters were in it.
- [ ] Given a Prefect server with no flow runs at all, then `GET /pipeline/sources` still returns
      six sources, each with `"records": null`, and HTTP **200**.
- [ ] Given a source whose parse stage has completed, then `records.count` is a positive integer
      matching that run's own log line, and carries the `flow` and `measured_at` it came from.
      (These are live values that change with every pipeline pass — the criterion is that the
      number equals what the log says, not that it equals any fixed figure.)
- [ ] Given `GET /pipeline/sources/{id}`, then the parse stage and the unify stage each report
      their own count from their own log — two separate numbers, never silently reconciled into
      one. They legitimately differ: on 2026-09-01 Research Collection parsed 306'939 records but
      contributed 293'374 at unify.
- [ ] When the log parser finds no matching line, then the field is `null` — never `0`, never an
      estimate, never a value carried over from another stage.
- [ ] Given `GET /pipeline/runs?state=RUNNING`, then only runs whose state is `RUNNING` are
      returned.
- [ ] Given `GET /pipeline/runs` with no parameters, then at most 50 runs are returned, newest
      first by start time.
- [ ] Given an unknown source id, when `GET /pipeline/sources/{id}` is called, then **404** with
      `{"detail": ...}` naming the known ids.
- [ ] Given an unreachable or slow Prefect server, then every endpoint answers **502** with
      `{"detail": ...}` within roughly 10 seconds — never an open-ended hang.
- [ ] Given a request without a valid `x-api-key` header, then every endpoint answers **401**,
      using the same key as `/commands/*`.
- [ ] No endpoint ever issues a request to Prefect other than a read: `GET`, or `POST` to a
      `.../filter` or `.../count` path.

## API sketch

All three endpoints require `x-api-key` (the same shared secret as `/commands/*`, see
[ADR 0005](../adr/0005-shared-secret-internal-api-key.md)) and are read-only.

```
GET /pipeline/sources

  → 200 {
      "fetched_at": "2026-09-06T09:12:44Z",
      "sources": [
        {
          "id": "slsp_eth",
          "label": "SLSP ETH (Alma IZ)",
          "description": "Alma MARC 21 for the ETH IZ over OAI-PMH -> slsp_eth_*.",
          "records": {
            "count": 4415363,
            "origin": "flow-run-log",
            "flow": "Parse: ALMA ETH",
            "measured_at": "2026-09-01T07:07:05Z"
          },
          "stages": [
            {
              "stage": "harvest",
              "deployment": "Harvester: SLSP ETH",
              "description": "Alma MARC 21 for the ETH IZ over OAI-PMH -> slsp_eth_*.",
              "schedule": null,
              "paused": false,
              "last_run": null
            },
            {
              "stage": "parse",
              "deployment": "Parse: ALMA ETH",
              "description": "MARC 21 -> alma/ready/eth.parquet.",
              "schedule": null,
              "paused": false,
              "last_run": {
                "id": "7a6aca84-3de7-4973-ba0f-ed03023e46b2",
                "name": "spirited-beetle",
                "state": "COMPLETED",
                "state_name": "Completed",
                "started_at": "2026-09-01T06:34:54Z",
                "ended_at": "2026-09-01T07:07:05Z",
                "duration_seconds": 1930.8
              }
            }
          ]
        }
      ]
    }
  → 401 {"detail": "Missing API key."}
  → 502 {"detail": "Prefect API unreachable: ..."}


GET /pipeline/sources/{source_id}

  Same shape as one entry above, plus per-stage `metrics` read from that stage's own run log:

  → 200 {
      "fetched_at": "...",
      "source": {
        "id": "research_collection",
        ...
        "stages": [
          {"stage": "harvest", ..., "metrics": null},
          {"stage": "parse", ...,
           "metrics": {"records": 306939,
                       "matched_line": "Total records: 306939"}},
          {"stage": "unify", "deployment": "Merge: Sources", ...,
           "metrics": {"records": 293374,
                       "matched_line": "Loading rc: 293,374 rows in 1 batch(es)..."}}
        ]
      }
    }
  → 404 {"detail": "Unknown source 'x'. Known: slsp_eth, slsp_network, epics, erara,
                    research_collection, semantic_scholar."}


GET /pipeline/runs?limit=50&state=RUNNING,FAILED

    limit  integer, 1..200, default 50
    state  comma-separated Prefect state types; omitted means all
           SCHEDULED PENDING RUNNING COMPLETED FAILED CANCELLED CANCELLING CRASHED PAUSED

  → 200 {
      "fetched_at": "...",
      "total": 17,
      "runs": [
        {
          "id": "c1f6ce49-cb72-4ead-99db-b71a95dc1a0e",
          "name": "orange-corgi",
          "deployment": "Deduplicate: Unified",
          "source_id": null,
          "stage": "deduplicate",
          "state": "RUNNING",
          "state_name": "Running",
          "started_at": "2026-09-02T17:07:51Z",
          "ended_at": null,
          "duration_seconds": 79444.4,
          "run_count": 1,
          "next_scheduled_start_time": null
        }
      ]
    }
  → 400 {"detail": "Unknown state 'X'. Known: SCHEDULED, PENDING, ..."}
```

`total` is the number of runs matching the filter on the server, which may exceed the number
returned under `limit`.

`source_id` is `null` for the five cross-source deployments (`Merge: ALMA`, `Merge: Sources`,
`Deduplicate: Unified`, `DAG Orchestrator`, `Slim Orchestrator`) — they belong to no single source.

### Source and stage mapping

Prefect has no concept of a data source. The mapping from its 19 deployments onto six sources lives
in this module and is keyed on the **entrypoint function name**, not the deployment name: a
deployment can be renamed in the Prefect UI, whereas the function name only changes with a code
change in `lumina-engine`.

| Source id | harvest | parse | hierarchy |
|---|---|---|---|
| `slsp_eth` | `harvester_slsp_eth` | `parse_alma_eth` | — |
| `slsp_network` | `harvester_slsp_network` | `parse_alma_network` | — |
| `epics` | `harvester_e_pics` | `parse_epics` | — |
| `erara` | `harvester_e_rara` | `parse_erara` | `hierarchy_erara` |
| `research_collection` | `harvester_research_collection` | `parse_rc` | — |
| `semantic_scholar` | `harvester_semantic_scholar` | `parse_semantic_scholar` | — |

Every source additionally gets a shared `unify` stage backed by `merge_sources`, because that
flow's log carries the per-source row counts.

Five deployments belong to no single source and are reported with `"source_id": null`:

| Entrypoint | Stage | Why it is not per-source |
|---|---|---|
| `merge_alma` | `merge` | Folds SLSP ETH and SLSP Network into one record per work |
| `hierarchy_alma` | `hierarchy` | Runs on the already-merged ALMA set, not on either source alone |
| `merge_sources` | `unify` | Processes all sources at once |
| `deduplicate_unified` | `deduplicate` | Cross-source by definition |
| `dag_orchestrator`, `slim_orchestrator` | `orchestrate` | Drive the whole pipeline |

`hierarchy_erara` is the one hierarchy step that *is* source-specific: it runs on e-rara alone.

### Where the numbers come from

Prefect stores **no artifacts and no task runs** on this server, so there is no structured place to
read record counts from. They exist only as free text in the flow-run logs. Three patterns are
matched, each bound to one specific flow so a line from an unrelated flow can never be misread:

| Pattern | Flow | Example |
|---|---|---|
| `^Total records:\s*([\d,']+)$` | `Parse: *` | `Total records: 4415363` |
| `^Parsing ([\d,']+) rows in \d+ batch` | `Parse: Semantic Scholar` | `Parsing 237,167,341 rows in 48 batch(es)...` |
| `^\s*Loading (\w+):\s*([\d,']+) rows in ` | `Merge: Sources` | `Loading rc: 293,374 rows in 1 batch(es)...` |

Prefect rejects a `logs/filter` limit above 200, so the first 200 lines of a run are read, sorted
ascending. Every pattern above matches within the first dozen lines of its flow.

Deliberately **not** parsed: the `doi: 566,389 pairs` / `mmsid: 36,423 pairs` lines from
`Deduplicate: Unified`. Those are deduplication key statistics, not source holdings; presenting
them as record counts would be wrong.

## Known limitations

- **Log parsing is brittle by construction.** Rewording a log message in `lumina-engine` silently
  turns a count into `null`. That is the designed failure mode — a missing number, never a wrong
  one. **The durable fix belongs in `lumina-engine`:** publish these counts as Prefect artifacts
  (`create_table_artifact`), and this module can read them as data instead of prose.
- **The run history on this Prefect server starts 2026-09-01T06:34:02**, when its metadata database
  was created. Prefect 3 OSS has no flow-run retention (`server.events.retention_period = P7D`
  covers events only), so nothing is being deleted — but earlier runs are simply not there. The run
  section will look sparse until more weekly runs accumulate.
- **A run's stage is inferred from its deployment.** Prefect records no link between an orchestrator
  run and the runs it triggers (`parent_task_run_id` is `null` throughout), so runs belonging to one
  pipeline pass cannot be grouped.
- **Prefect becomes an availability dependency.** When it is down, these endpoints return 502 while
  the rest of the API is healthy. See [ADR 0007](../adr/0007-prefect-read-only-proxy.md).

## Out of scope

- **Any write to Prefect** — triggering runs, pausing deployments, cancelling. This module is
  read-only, and [ADR 0007](../adr/0007-prefect-read-only-proxy.md) makes that a property of the
  design rather than a habit.
- **Caching.** Every request queries Prefect afresh; response caching is Apigee's job.
- **A separate API key.** `/pipeline/*` uses the same `x-api-key` as `/commands/*`.
- **Grouping runs into pipeline passes** — Prefect provides no linkage for it, and a time-window
  heuristic would group wrongly.
- **Time-series and aggregate history** (`/ui/flow_runs/history`).
- **Reading MongoDB, Parquet files, or the Cloud SQL target directly** for authoritative holdings.
  This module reports what Prefect observed, not what the data stores contain.
