# 0005 — Shared-secret internal API key for `/commands/*`

**Status:** Accepted
**Date:** 2026-04-22
**Deciders:** Germano Giuliani

> *Retroactive record.* Implemented 2026-04-22 (`feat: Add API key authentication to commands
> router with header-based verification and Secret Manager integration`); written 2026-07-31 from
> `app/auth.py`. Context and alternatives are reconstructed.

## Context

The Cloud Run service is deployed `--allow-unauthenticated` ([0001](0001-fastapi-on-cloud-run.md))
and is therefore reachable by anyone who discovers its URL. Consumer identity and quota are handled
one layer up by Apigee ([0004](0004-apigee-as-sole-public-ingress.md)), which injects a credential
on the way through.

The backend still needs something: the endpoints it exposes trigger multi-minute jobs, spend money
on OpenAI embeddings, and write to a production vector index. Unauthenticated access to
`/commands/upsert-pinecone` is a billing incident and a data-integrity incident at the same time.

At the same time, monitoring and deployment tooling needs to check service health without holding a
credential.

## Decision

We will protect **all `/commands/*` endpoints with a single shared secret** presented in the
`x-api-key` header and compared against the `INTERNAL_API_KEY` environment variable.

- The check lives in `app/auth.py` as a FastAPI dependency and is attached **at the router level**
  in `app/routers/commands.py`, so it applies to every current and future command endpoint by
  default rather than per-decorator.
- **Utility endpoints (`/`, `/health`, `/version`) stay unauthenticated**, so Cloud Run health
  checks and uptime monitoring work without a credential.
- Responses distinguish the failure modes: `401 Missing API key`, `401 Invalid API key`, and
  `500 INTERNAL_API_KEY not configured` — the last so that a misconfigured deployment fails loudly
  rather than accepting every request.
- The key's value comes from Secret Manager in production
  ([0006](0006-secrets-in-secret-manager.md)) and from `.env` locally.

## Consequences

**Easier**

- Ten lines of code, no dependencies, no token library, no key server.
- Router-level attachment means a new command endpoint cannot accidentally ship unprotected.
- Works identically for Apigee, Postman, and `curl`, so local testing matches production behaviour.
- Refusing to run without a configured key removes a whole class of silent misconfiguration.

**Harder**

- **The backend has no idea who is calling.** Every consumer arrives as the same key, so logs cannot
  attribute a run to a person or system. When an unexpected upsert overwrites a namespace, there is
  nothing in this service's logs to say who did it — that evidence exists only in Apigee.
- **Rotation is all-or-nothing.** One key, one value, no support for accepting an old and a new key
  simultaneously, so a rotation is a hard cutover coordinated with Apigee rather than a rolling
  change. See [runbook 02](../runbooks/02-rotate-secrets.md).
- **The comparison is `!=`, not constant-time.** A timing side channel on an internet-facing
  comparison is not practically exploitable through network jitter, but `hmac.compare_digest` is a
  drop-in replacement with no downside and would remove the question entirely.
- **A leaked key is total access.** There is no scope, no expiry, and no per-endpoint restriction —
  the same secret that reads `/version` data can trigger a full re-embed.
- Anything that can read the service's environment (a shell in the container, a future debug
  endpoint, an exception handler that dumps `os.environ`) reads the key.

## Alternatives considered

**Cloud Run IAM / OIDC tokens** — Google-managed identity, per-caller service accounts, automatic
rotation, and identity visible in Cloud Audit Logs. Strictly better on every security axis.
Rejected for the initial implementation because it requires configuring Apigee to mint and attach
Google-signed tokens, and because it would make direct `curl` testing during development
substantially more awkward. Revisit together with
[0004](0004-apigee-as-sole-public-ingress.md)'s bypass problem — they have the same fix.

**A JWT issued by Apigee carrying consumer claims** — would give the backend real per-consumer
identity for logging and per-endpoint authorization. Rejected as disproportionate for a service with
a handful of trusted internal consumers; worth reconsidering the moment an audit trail of *who ran
which command* is required.

**mTLS between Apigee and Cloud Run** — strong mutual authentication, no bearer secret to leak.
Rejected: certificate lifecycle management for a two-party link is more operational burden than the
threat model warrants.

**No backend authentication, relying on Apigee alone** — rejected outright. The Cloud Run URL is
public; this would leave the pipeline and its OpenAI budget open to anyone who found it.
