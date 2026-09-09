# 0009 — One shared keep-alive client for Prefect reads

**Status:** Accepted
**Date:** 2026-09-09
**Deciders:** Germano Giuliani

Amends [0007](0007-prefect-read-only-proxy.md): replaces its decision to create an HTTP client per
request. Everything else in 0007 stands.

## Context

[0007](0007-prefect-read-only-proxy.md) chose a fresh `httpx.AsyncClient` for every request, on the
reasoning that connection pooling *within* one request's fan-out was enough and a shared client
would be a new pattern without a payoff. That held on the ETH network. It failed from Cloud Run.

On 2026-09-09 the deployed `/pipeline/*` endpoints started answering 502 —
`Prefect API unreachable: All connection attempts failed` — most of the time, while the same code
on a laptop inside ETH never failed. The failures were immediate (80–100 ms), so refusals rather
than timeouts; after two and a half minutes of quiet the first few requests succeeded, then
everything was refused again.

Measured against the live Prefect server, the per-request client opens **13 new TCP connections
for `GET /sources` and 15 for one Studio page load, all within about 50 milliseconds**, because
`asyncio.gather` fires a dozen reads at once and each one dials fresh. From Cloud Run those
connections leave through Cloud NAT with one static IP and, by default, 64 ports per instance held
for 120 s after close. Four page loads consume the budget; a per-source session-rate limit on the
ETH perimeter would trip on the first. The numbers fit the NAT explanation precisely, the immediate
refusal fits a firewall better, and the logs did not yet say which — but both are the same defect
seen from two sides: the burst.

## Decision

We will use **one `httpx.AsyncClient` per worker process**, created lazily on first use and never
closed, with **four keep-alive connections** and no other limit. All Prefect reads go through it.

- `asyncio.gather` is untouched. The fan-out is the same; httpx queues it through four connections
  instead of opening one per call.
- Keep-alive expiry is **5 seconds** — the Prefect server runs Uvicorn with its default idle
  timeout, and holding a socket the peer has already closed buys nothing. Measured: a connection
  is reused after 3 s of idle and redialled after 6 s, cleanly, without an error.
- No application lifespan. The client is a module-level singleton; a worker process that ends takes
  it along. [0008](0008-stage-reports-from-cloud-sql.md) introduces a lifespan for a database pool,
  and the client can move into it then; that is not a reason to add one now.
- The router logs connection failures with `%r`, so the underlying `OSError` and its errno reach
  Cloud Run's logs. `[Errno 111] Connection refused` names a firewall; `[Errno 99] Cannot assign
  requested address` names exhausted ports. The next incident will say which.

## Consequences

**Easier**

- Four new connections per process per burst instead of fifteen. Within any per-source limit that
  a dashboard could plausibly meet, and within the NAT port budget with room to spare.
- Requests that arrive within 5 s of each other reuse warm connections and skip the handshake.

**Harder**

- **State survives between requests.** A wedged connection in the pool affects the next request,
  not only the one that broke it. httpx discards connections the peer has closed, which is the
  common case; a half-open one would live until its next use fails.
- **The pool is per process, not per service.** Gunicorn runs several workers; Cloud Run runs
  several instances. Each has its own four. The real ceiling is `workers × instances × 4`, and
  `--max-instances` on the deploy is what bounds it.
- The client is never closed. On Cloud Run that is harmless — the process is killed, not shut
  down — but a test harness that expects a clean event-loop teardown would have to close it.
- **This does not lift the limit; it stays under it.** A polling interval short enough to open
  four fresh connections every few seconds could still reach a strict enough limit. If that
  happens, Cloud NAT's dynamic port allocation and shorter TIME_WAIT are the infrastructure side of
  the same fix, and asking ETH network operations about the perimeter rule is the other.

## Alternatives considered

**Keep the per-request client, lower the concurrency** — replace `asyncio.gather` with a small
semaphore. Rejected: it slows every request to solve a problem that only exists between requests,
and a page load would still open a fresh set each time.

**A client per request with a shared transport** — the same effect with more moving parts.
Rejected as the same decision in a costume.

**Fix it in infrastructure only** — dynamic NAT ports, a firewall exemption for the static IP.
Not rejected, but not sufficient alone: it raises the ceiling without stopping the code from
running at it. Recorded above as the complement, for the humans.

**Retry on refusal** — masks the symptom, adds latency, and hammers a limit that is already
refusing. Rejected.
