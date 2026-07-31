# 0006 — Secrets in Secret Manager, injected as environment variables at deploy time

**Status:** Accepted
**Date:** 2026-04-22
**Deciders:** Germano Giuliani

> *Retroactive record.* Implemented 2026-04-22 alongside the auth work; written 2026-07-31 from
> `deploy.sh`, `setup-secrets.sh`, and `app/config.py`. Context and alternatives are reconstructed.

## Context

The service holds three credentials, each of which is either expensive or dangerous to leak:

| Secret | Leak consequence |
|--------|------------------|
| `OPENAI_API_KEY` | Direct, uncapped spend on ETH's OpenAI account |
| `PINECONE_API_KEY` | Read and write access to production vector indexes |
| `INTERNAL_API_KEY` | Full access to every `/commands/*` endpoint ([0005](0005-shared-secret-internal-api-key.md)) |

The repository is on GitHub under `eth-library`. Deployment is a one-command script run from a
developer laptop ([0001](0001-fastapi-on-cloud-run.md)), and the build is a source-based buildpack
build, which means anything in the working directory can end up in the image layer.

## Decision

We will store all three secrets in **Google Cloud Secret Manager** and have Cloud Run inject them as
**environment variables at deploy time**.

- [`deploy.sh`](../../deploy.sh) passes `--set-secrets=NAME=SECRET_NAME:latest` for each of the
  three. Cloud Run resolves the version when the revision is created.
- [`setup-secrets.sh`](../../setup-secrets.sh) reads the developer's local `.env`, creates each
  secret if it does not exist (automatic replication), and adds the current value as a **new secret
  version**.
- `app/config.py` reads everything through `os.getenv` with `python-dotenv` loading `.env` first, so
  **the same code path serves local and production** — locally the values come from `.env`, in Cloud
  Run from the injected variables.
- `.env` is listed in `.gitignore`; [`.env.example`](../../.env.example) is committed with
  placeholder values as the template.
- The Cloud Run runtime service account requires `roles/secretmanager.secretAccessor`, granted once
  per project ([runbook 03](../runbooks/03-gcp-project-bootstrap.md)).

## Consequences

**Easier**

- No secret is ever in the repository, the container image, or the Cloud Run revision configuration
  — the revision stores a *reference* to a secret version, not its value.
- Secret Manager keeps every version, so a bad rotation can be traced and an old value recovered.
- Access to secrets is IAM-controlled and logged in Cloud Audit Logs.
- Identical configuration code locally and in production; nothing to special-case.

**Harder**

- **`:latest` is resolved at revision creation, not at request time.** Adding a new secret version
  changes nothing until the service is redeployed. This is the single most common operational
  surprise here and the reason [runbook 02](../runbooks/02-rotate-secrets.md) ends with a deploy
  step.
- **The developer's `.env` is the de facto source of truth for secret values.** `setup-secrets.sh`
  pushes laptop → cloud, never the reverse, so the authoritative copy of every production credential
  lives unencrypted on developer machines. Whoever holds the newest `.env` holds the keys, and a
  laptop loss is a rotation event.
- Secrets are in the container's process environment, so anything that can read `os.environ` — a
  debug endpoint, a crash dump, a verbose exception handler — can read them.
- A missing IAM binding surfaces as a revision that fails to start, with a cause that is not obvious
  from the application logs.
- `setup-secrets.sh` parses `.env` with `grep`/`cut` and strips CR/LF. Values containing `=` survive
  (`cut -d'=' -f2-`), but quoting, `#` comments on the same line, and multi-line values would not —
  a constraint on what may be put in `.env`, and one that fails silently.

## Alternatives considered

**Secrets mounted as files instead of environment variables** — Cloud Run can mount a secret as a
volume, and with a mounted volume the value can be re-read without a new revision, which would remove
the redeploy-to-rotate step. Rejected for consistency with the twelve-factor `os.getenv` pattern that
`config.py` already uses for all other configuration; genuinely worth reconsidering if rotation
frequency increases.

**Fetching secrets from the Secret Manager API at runtime** — always current, no redeploy on
rotation. Rejected as added latency, an extra failure mode on every cold start, and client code to
maintain, for a service that is redeployed often anyway.

**Plain environment variables set directly on the service (`--set-env-vars`)** — simplest possible
approach. Rejected because the values would then be visible in the Cloud Run revision configuration
to anyone with `run.services.get`, and in the output of `gcloud run services describe`.

**A committed encrypted secrets file (SOPS, git-crypt)** — versioned alongside the code, reviewable
in a PR. Rejected as redundant when the platform provides a managed secret store, and it introduces
a key-encryption-key that itself needs distributing.
