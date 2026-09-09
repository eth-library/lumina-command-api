# app/routers/pipeline.py

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
import logging

import httpx

from app.auth import verify_api_key
from app.services.prefect_status import (
    RUNS_DEFAULT_LIMIT,
    get_runs,
    get_source,
    get_sources,
)

logger = logging.getLogger(__name__)

# Read-only status endpoints over the Lumina Engine's Prefect server (ADR 0007).
# Same x-api-key as /commands/*; the dependency lives on the router, so a new
# router has to declare it explicitly or it would be unauthenticated.
router = APIRouter(prefix="/pipeline", tags=["pipeline"], dependencies=[Depends(verify_api_key)])


def _root_cause(exc: BaseException) -> BaseException:
    """
    The innermost exception in the chain. httpx wraps the OS error three levels
    deep ("All connection attempts failed" twice, then the real one), and that
    innermost one is the only place the errno lives.
    """
    seen: set[int] = set()
    while id(exc) not in seen:
        seen.add(id(exc))
        nested = getattr(exc, "exceptions", None)  # ExceptionGroup
        following = (nested[0] if nested else None) or exc.__cause__ or exc.__context__
        if following is None:
            return exc
        exc = following
    return exc


def _unavailable(exc: Exception) -> JSONResponse:
    # An expected failure mode, not a defect in this service: log the cause, not a
    # stack trace that would repeat on every request for the duration of an outage.
    # The root cause carries the errno, and the errno names the culprit:
    # "[Errno 111] Connection refused" is a firewall, "[Errno 99] Cannot assign
    # requested address" is NAT port exhaustion (ADR 0009).
    logger.warning("Prefect API unreachable: %s — root cause: %r", exc, _root_cause(exc))
    return JSONResponse(status_code=502, content={"detail": f"Prefect API unreachable: {exc}"})


# 1️⃣ Sources overview
@router.get("/sources")
async def sources():
    try:
        return await get_sources()
    except httpx.HTTPError as exc:
        return _unavailable(exc)


# 2️⃣ One source in detail
@router.get("/sources/{source_id}")
async def source(source_id: str):
    try:
        return await get_source(source_id)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except httpx.HTTPError as exc:
        return _unavailable(exc)


# 3️⃣ Flow runs
@router.get("/runs")
async def runs(
    limit: int = RUNS_DEFAULT_LIMIT,
    state: str | None = Query(default=None, description="Comma-separated Prefect state types."),
    deployment: str | None = Query(
        default=None, description="Comma-separated deployment names, exactly as returned in `deployment`."
    ),
):
    states = [s.strip().upper() for s in state.split(",") if s.strip()] if state else None
    names = [d.strip() for d in deployment.split(",") if d.strip()] if deployment else None
    try:
        return await get_runs(limit=limit, states=states, deployment_names=names)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except httpx.HTTPError as exc:
        return _unavailable(exc)
