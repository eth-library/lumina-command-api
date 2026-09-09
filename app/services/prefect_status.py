# app/services/prefect_status.py

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

from app.config import Config

logger = logging.getLogger(__name__)

# -------------------------
# Constants
# -------------------------
PREFECT_TIMEOUT = 10.0  # seconds, per request
RUNS_DEFAULT_LIMIT = 50
RUNS_MAX_LIMIT = 200
# Prefect rejects a logs/filter limit above 200. Sorted ascending, so these are the
# first 200 lines of a run — which is where every count line we match appears.
LOG_FETCH_LIMIT = 200

PREFECT_STATE_TYPES = [
    "SCHEDULED", "PENDING", "RUNNING", "COMPLETED",
    "FAILED", "CANCELLED", "CANCELLING", "CRASHED", "PAUSED",
]

# Prefect has no concept of a data source. This maps its deployments onto the six
# sources of the Lumina Engine, keyed on the entrypoint *function* name rather than
# the deployment name: a deployment can be renamed in the Prefect UI, a function name
# only changes with a code change in lumina-engine. See docs/specs/04-prefect-pipeline-status.md.
SOURCES: dict[str, dict] = {
    "slsp_eth": {
        "label": "SLSP ETH (Alma IZ)",
        "stages": {"harvest": "harvester_slsp_eth", "parse": "parse_alma_eth"},
        "unify_key": "alma",
    },
    "slsp_network": {
        "label": "SLSP Network (Alma NZ)",
        "stages": {"harvest": "harvester_slsp_network", "parse": "parse_alma_network"},
        "unify_key": "alma",
    },
    "epics": {
        "label": "E-Pics",
        "stages": {"harvest": "harvester_e_pics", "parse": "parse_epics"},
        "unify_key": "epics",
    },
    "erara": {
        "label": "E-Rara",
        "stages": {
            "harvest": "harvester_e_rara",
            "parse": "parse_erara",
            "hierarchy": "hierarchy_erara",
        },
        "unify_key": "erara",
    },
    "research_collection": {
        "label": "Research Collection",
        "stages": {"harvest": "harvester_research_collection", "parse": "parse_rc"},
        "unify_key": "rc",
    },
    "semantic_scholar": {
        "label": "Semantic Scholar",
        "stages": {
            "harvest": "harvester_semantic_scholar",
            "parse": "parse_semantic_scholar",
        },
        "unify_key": "semscholar",
    },
}

# Deployments that belong to no single source.
CROSS_SOURCE_STAGES: dict[str, str] = {
    "merge_alma": "merge",
    "hierarchy_alma": "hierarchy",
    "merge_sources": "unify",
    "deduplicate_unified": "deduplicate",
    "load_postgres": "load",
    "dag_orchestrator": "orchestrate",
    "slim_orchestrator": "orchestrate",
}

# The flow whose log carries the per-source row counts at unify time.
UNIFY_ENTRYPOINT = "merge_sources"

# Which sources share one unify figure. 'Merge: ALMA' folds SLSP ETH and SLSP
# Network into one record per work before unify runs, so the log's `alma` line
# counts both of them together — it is larger than either source's parse count
# and identical under both. Every metrics block therefore names the sources its
# figure covers, so no client has to know this.
UNIFY_GROUPS: dict[str, list[str]] = {}
for _source_id, _source in SOURCES.items():
    UNIFY_GROUPS.setdefault(_source["unify_key"], []).append(_source_id)

# Record counts exist only as free text in flow-run logs — this Prefect server stores
# no artifacts and no task runs. Each pattern is bound to one kind of flow so a line
# from an unrelated flow can never be misread.
PARSE_COUNT_PATTERN = re.compile(r"^Total records:\s*([\d,']+)\s*$")
PARSE_S2_COUNT_PATTERN = re.compile(r"^Parsing ([\d,']+) rows in \d+ batch")
UNIFY_COUNT_PATTERN = re.compile(r"^\s*Loading (\w+):\s*([\d,']+) rows in ")


# -------------------------
# Prefect client (read-only)
# -------------------------
async def _post_read(client: httpx.AsyncClient, path: str, body: dict):
    """
    POST to a Prefect *read* endpoint.

    Prefect expresses its queries as POST bodies, so reading requires POST. Only
    `/filter` and `/count` paths are permitted here — this module has no code path
    that can write to Prefect (ADR 0007).
    """
    if not (path.endswith("/filter") or path.endswith("/count")):
        raise ValueError(f"Refusing to POST to non-read Prefect path: {path}")
    response = await client.post(f"{Config.PREFECT_API_URL}{path}", json=body)
    response.raise_for_status()
    return response.json()


# One client for the whole process, reused across requests. A client per request
# opened every connection fresh — 13 for /sources, 15 for a Studio page load, all
# within ~50 ms — which tripped a per-source connection limit between Cloud Run
# and the Prefect host (2026-09-09: immediate refusals after a few requests).
# Four keep-alive connections carry the same fan-out; asyncio.gather simply
# queues through them. Uvicorn on the Prefect side drops idle connections after
# 5 s, so the expiry matches that rather than holding sockets the peer has closed.
# Never closed: it lives as long as the worker process. See ADR 0009.
_shared_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            timeout=PREFECT_TIMEOUT,
            limits=httpx.Limits(
                max_connections=4,
                max_keepalive_connections=4,
                keepalive_expiry=5.0,
            ),
        )
    return _shared_client


# -------------------------
# Helpers
# -------------------------
def _entrypoint_function(deployment: dict) -> str:
    """'src/lumina/orchestration/flows.py:parse_alma_eth' -> 'parse_alma_eth'."""
    return (deployment.get("entrypoint") or "").rsplit(":", 1)[-1]


def _cron_schedules(deployment: dict) -> list[str]:
    schedules = deployment.get("schedules") or []
    return [
        cron
        for schedule in schedules
        if (cron := (schedule.get("schedule") or {}).get("cron"))
    ]


def _to_int(raw: str) -> int:
    """'237,167,341' or "237'167'341" -> 237167341."""
    return int(raw.replace(",", "").replace("'", ""))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _shape_run(run: dict) -> dict:
    """
    One flow run. The deployment it belongs to is added by /pipeline/runs; nested
    under a stage it would only repeat what the stage already says.
    """
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "state": run.get("state_type"),
        "state_name": run.get("state_name"),
        "started_at": run.get("start_time"),
        "ended_at": run.get("end_time"),
        # estimated_run_time, not total_run_time: the latter sums only *completed*
        # intervals and is 0.0 for a run still in progress. estimated_run_time adds
        # the time spent in the current state, and for a finished run the two are
        # identical — so it is correct in every state.
        "duration_seconds": run.get("estimated_run_time"),
        "run_count": run.get("run_count"),
        "next_scheduled_start_time": run.get("next_scheduled_start_time"),
    }


# -------------------------
# Prefect reads
# -------------------------
async def _fetch_deployments(client: httpx.AsyncClient) -> dict[str, dict]:
    """All deployments, keyed by entrypoint function name."""
    deployments = await _post_read(client, "/deployments/filter", {"limit": 200})
    return {_entrypoint_function(d): d for d in deployments}


async def _fetch_last_run(client: httpx.AsyncClient, deployment_id: str) -> dict | None:
    """The most recently started run of one deployment, or None if it has never run."""
    runs = await _post_read(
        client,
        "/flow_runs/filter",
        {
            "deployments": {"id": {"any_": [deployment_id]}},
            "limit": 1,
            "sort": "START_TIME_DESC",
        },
    )
    return runs[0] if runs else None


async def _fetch_run_logs(client: httpx.AsyncClient, flow_run_id: str) -> list[str]:
    logs = await _post_read(
        client,
        "/logs/filter",
        {
            "logs": {"flow_run_id": {"any_": [flow_run_id]}},
            "limit": LOG_FETCH_LIMIT,
            "sort": "TIMESTAMP_ASC",
        },
    )
    return [entry.get("message") or "" for entry in logs]


# -------------------------
# Log parsing
# -------------------------
def _parse_stage_records(messages: list[str]) -> dict | None:
    """
    Record count from a Parse flow's log.

    Returns None when no line matches — a missing number, never a guessed one.
    """
    for message in messages:
        for pattern in (PARSE_COUNT_PATTERN, PARSE_S2_COUNT_PATTERN):
            if match := pattern.match(message):
                return {"records": _to_int(match.group(1)), "matched_line": message.strip()}
    return None


def _parse_unify_records(messages: list[str]) -> dict[str, dict]:
    """
    Per-source row counts from the 'Merge: Sources' log, keyed by its own source key
    ('alma', 'epics', 'erara', 'rc', 'semscholar').
    """
    counts: dict[str, dict] = {}
    for message in messages:
        if match := UNIFY_COUNT_PATTERN.match(message):
            counts[match.group(1)] = {
                "records": _to_int(match.group(2)),
                "matched_line": message.strip(),
            }
    return counts


# -------------------------
# 1. Sources overview
# -------------------------
async def get_sources() -> dict:
    """
    The six data sources with their pipeline stages, the last run of each stage, and
    the record count observed at parse time.
    """
    client = _client()
    # --- 1. Deployments, and the last run of every deployment we care about ---
    deployments = await _fetch_deployments(client)

    wanted = {
        entrypoint
        for source in SOURCES.values()
        for entrypoint in source["stages"].values()
    }
    present = [e for e in wanted if e in deployments]
    last_runs = dict(
        zip(
            present,
            await asyncio.gather(
                *(_fetch_last_run(client, deployments[e]["id"]) for e in present)
            ),
        )
    )

    # --- 2. Record counts from each parse run's log ---
    parse_runs = {
        source_id: last_runs.get(source["stages"].get("parse"))
        for source_id, source in SOURCES.items()
    }
    with_runs = {s: r for s, r in parse_runs.items() if r}
    logs = dict(
        zip(
            with_runs,
            await asyncio.gather(
                *(_fetch_run_logs(client, run["id"]) for run in with_runs.values())
            ),
        )
    )

    # --- 3. Shape the response ---
    sources = []
    for source_id, source in SOURCES.items():
        parse_run = parse_runs.get(source_id)
        records = None
        if source_id in logs and (parsed := _parse_stage_records(logs[source_id])):
            records = {
                "count": parsed["records"],
                "origin": "flow-run-log",
                "flow": deployments[source["stages"]["parse"]].get("name"),
                "measured_at": parse_run.get("end_time"),
            }

        sources.append(
            {
                "id": source_id,
                "label": source["label"],
                "description": _source_description(deployments, source),
                "records": records,
                "stages": _shape_stages(deployments, source, last_runs),
            }
        )

    return {"fetched_at": _now(), "sources": sources}


def _source_description(deployments: dict[str, dict], source: dict) -> str | None:
    """The harvester's own description — Prefect's closest thing to source metadata."""
    harvester = deployments.get(source["stages"].get("harvest", ""))
    return harvester.get("description") if harvester else None


def _shape_stages(
    deployments: dict[str, dict],
    source: dict,
    last_runs: dict[str, dict | None],
) -> list[dict]:
    stages = []
    for stage, entrypoint in source["stages"].items():
        deployment = deployments.get(entrypoint)
        if not deployment:
            logger.warning("No Prefect deployment for entrypoint '%s'", entrypoint)
            continue
        run = last_runs.get(entrypoint)
        stages.append(
            {
                "stage": stage,
                "deployment": deployment.get("name"),
                "description": deployment.get("description"),
                "schedule": _cron_schedules(deployment) or None,
                "paused": deployment.get("paused"),
                "last_run": _shape_run(run) if run else None,
            }
        )
    return stages


# -------------------------
# 2. One source in detail
# -------------------------
async def get_source(source_id: str) -> dict:
    """
    One source, with a `metrics` block per stage read from that stage's own run log.

    Raises ValueError for an unknown source id.
    """
    if source_id not in SOURCES:
        raise ValueError(
            f"Unknown source '{source_id}'. Known: {', '.join(SOURCES)}."
        )

    source = SOURCES[source_id]

    client = _client()
    deployments = await _fetch_deployments(client)

    # --- 1. Last run of every stage of this source, plus the shared unify run ---
    entrypoints = [e for e in source["stages"].values() if e in deployments]
    unify_deployment = deployments.get(UNIFY_ENTRYPOINT)
    if unify_deployment:
        entrypoints.append(UNIFY_ENTRYPOINT)

    last_runs = dict(
        zip(
            entrypoints,
            await asyncio.gather(
                *(_fetch_last_run(client, deployments[e]["id"]) for e in entrypoints)
            ),
        )
    )

    # --- 2. Logs of every stage that has actually run ---
    ran = {e: r for e, r in last_runs.items() if r}
    logs = dict(
        zip(
            ran,
            await asyncio.gather(
                *(_fetch_run_logs(client, run["id"]) for run in ran.values())
            ),
        )
    )

    # --- 3. Shape stages, attaching metrics where a log line matched ---
    unify_counts = _parse_unify_records(logs.get(UNIFY_ENTRYPOINT, []))

    stages = _shape_stages(deployments, source, last_runs)
    for stage in stages:
        entrypoint = source["stages"][stage["stage"]]
        metrics = _parse_stage_records(logs[entrypoint]) if entrypoint in logs else None
        # A per-source stage counts this source alone.
        stage["metrics"] = {**metrics, "covers": [source_id]} if metrics else None

    if unify_deployment:
        unify_run = last_runs.get(UNIFY_ENTRYPOINT)
        # The unify figure may cover more than one source — see UNIFY_GROUPS.
        unify_metrics = unify_counts.get(source["unify_key"])
        stages.append(
            {
                "stage": "unify",
                "deployment": unify_deployment.get("name"),
                "description": unify_deployment.get("description"),
                "schedule": _cron_schedules(unify_deployment) or None,
                "paused": unify_deployment.get("paused"),
                "last_run": _shape_run(unify_run) if unify_run else None,
                "metrics": {
                    **unify_metrics,
                    "covers": UNIFY_GROUPS[source["unify_key"]],
                }
                if unify_metrics
                else None,
            }
        )

    return {
        "fetched_at": _now(),
        "source": {
            "id": source_id,
            "label": source["label"],
            "description": _source_description(deployments, source),
            "stages": stages,
        },
    }


# -------------------------
# 3. Flow runs
# -------------------------
async def get_runs(
    limit: int = RUNS_DEFAULT_LIMIT,
    states: list[str] | None = None,
    deployment_names: list[str] | None = None,
) -> dict:
    """
    The most recent flow runs across all deployments, newest first.

    Raises ValueError for an out-of-range limit, an unknown state, or an unknown
    deployment name.
    """
    if not 1 <= limit <= RUNS_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {RUNS_MAX_LIMIT}, got {limit}.")

    run_filter: dict = {}
    if states:
        unknown = [s for s in states if s not in PREFECT_STATE_TYPES]
        if unknown:
            raise ValueError(
                f"Unknown state '{unknown[0]}'. Known: {', '.join(PREFECT_STATE_TYPES)}."
            )
        run_filter["flow_runs"] = {"state": {"type": {"any_": states}}}

    client = _client()
    deployments = await _fetch_deployments(client)

    # Validated against what Prefect actually has, so a typo is rejected rather
    # than silently returning an empty — but plausible-looking — list.
    if deployment_names:
        known = sorted(d["name"] for d in deployments.values())
        unknown = [n for n in deployment_names if n not in known]
        if unknown:
            raise ValueError(
                f"Unknown deployment '{unknown[0]}'. Known: {', '.join(known)}."
            )
        run_filter["deployments"] = {"name": {"any_": deployment_names}}

    runs, total = await asyncio.gather(
        _post_read(
            client,
            "/flow_runs/filter",
            {**run_filter, "limit": limit, "sort": "START_TIME_DESC"},
        ),
        _post_read(client, "/flow_runs/count", run_filter),
    )

    by_id = {d["id"]: d for d in deployments.values()}
    entrypoint_by_id = {d["id"]: e for e, d in deployments.items()}
    source_by_entrypoint = {
        entrypoint: source_id
        for source_id, source in SOURCES.items()
        for entrypoint in source["stages"].values()
    }
    stage_by_entrypoint = {
        entrypoint: stage
        for source in SOURCES.values()
        for stage, entrypoint in source["stages"].items()
    }

    shaped = []
    for run in runs:
        deployment = by_id.get(run.get("deployment_id"))
        entrypoint = entrypoint_by_id.get(run.get("deployment_id"))
        shaped.append(
            {
                **_shape_run(run),
                "deployment": deployment.get("name") if deployment else None,
                "source_id": source_by_entrypoint.get(entrypoint),
                "stage": stage_by_entrypoint.get(entrypoint)
                or CROSS_SOURCE_STAGES.get(entrypoint),
            }
        )

    return {"fetched_at": _now(), "total": total, "runs": shaped}
