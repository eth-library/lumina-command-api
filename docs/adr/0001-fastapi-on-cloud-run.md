# 0001 — FastAPI on Cloud Run, deployed from source with Buildpacks

**Status:** Accepted
**Date:** 2026-02-23
**Deciders:** Germano Giuliani

> *Retroactive record.* Implemented in the initial commit (2026-02-23, `Initial commit: FastAPI
> skeleton` and `Add Procfile for Cloud Run start command`); written 2026-07-31 from the code and
> `deploy.sh`. The Decision section describes what the system verifiably does. Context and
> alternatives are reconstructed.

## Context

The Lumina initiative needs a service that runs data transformation and enrichment jobs on ETH
Library metadata on demand. The workload has a distinct shape:

- **Bursty and infrequent.** Pipelines run when a dataset is refreshed, not continuously. Between
  runs the service does nothing.
- **Long per request.** A full ETH UDK run is ~63'000 records through eleven transformation steps;
  an embedding run adds hundreds of OpenAI round-trips. Minutes, not milliseconds.
- **Memory-hungry.** The pipeline holds the entire dataset in memory as Python objects and builds
  several `sys → record` lookup maps over it.
- **Python-bound.** The data-processing ecosystem the team relies on (pandas, the OpenAI and
  Pinecone SDKs) is Python.

ETH Library operates on Google Cloud. The team is small, and there is no platform engineer to
maintain container base images or a Kubernetes cluster.

## Decision

We will build the service as a **FastAPI** application and run it on **Google Cloud Run** in
`europe-west6` (Zurich).

- Production process is **Gunicorn with `uvicorn.workers.UvicornWorker`**, defined in
  [`Procfile`](../../Procfile). Local development uses Uvicorn directly with `--reload`.
- Deployment is **from source** — `gcloud run deploy --source .` in [`deploy.sh`](../../deploy.sh)
  — using Google Cloud Buildpacks. There is deliberately **no Dockerfile**; the buildpack detects
  Python from `requirements.txt`.
- The service is provisioned with **8 GiB memory, 4 vCPU, and a 3600 s request timeout**, sized for
  the full-dataset run.
- The service is deployed `--allow-unauthenticated`; access control is handled at the edge
  ([0004](0004-apigee-as-sole-public-ingress.md)) and by a shared key
  ([0005](0005-shared-secret-internal-api-key.md)).
- Because Cloud Run caps request bodies at **~32 MB**, endpoints accept **gzip-compressed uploads**
  (`.json.gz` / `.csv.gz`, or a `Content-Encoding: gzip` header) as well as plain files.

## Consequences

**Easier**

- Scale-to-zero: no cost between runs, no idle instance to babysit.
- No Dockerfile, no base-image patching, no registry hygiene work.
- FastAPI generates the OpenAPI document and Swagger UI at `/docs` for free, which is what
  consumers and Apigee are built against.
- One-command deploy that any team member can run from a laptop.

**Harder**

- **The 32 MB request cap is a hard architectural constraint.** It is the reason gzip handling
  exists in `read_json_file` and `run_pinecone_upsert`. Any new bulk endpoint inherits it. Growth
  beyond what gzip buys will force a move to GCS-staged uploads (client uploads to a bucket, passes
  an object path).
- **The 3600 s timeout is the ceiling on any single command.** A dataset that outgrows it cannot be
  processed by adding memory; it requires chunking or a move to Cloud Run Jobs.
- **Instances are ephemeral and horizontally scaled, so no in-process state may be relied on.** The
  polling job store in `app/routers/commands.py` is an in-memory dict and therefore violates this:
  a status poll may land on a different instance than the one running the job, and any revision
  restart loses all jobs. This is a known defect of the current implementation, not a property of
  the platform choice.
- The buildpack selects the Python runtime implicitly. Upgrades happen without an explicit change
  in this repo, and there is no control over OS-level packages.
- `--allow-unauthenticated` puts the service on the public internet. See
  [0004](0004-apigee-as-sole-public-ingress.md) and [0005](0005-shared-secret-internal-api-key.md)
  for what stands between the internet and the pipeline.
- 8 GiB / 4 vCPU is billed for the whole request duration, including the long stretches spent
  waiting on OpenAI. A large embedding run is the dominant cost driver.

## Alternatives considered

**Cloud Run Jobs instead of a Service** — the better structural fit for long batch work: no request
timeout, no 32 MB body limit, built for run-to-completion. Rejected because the deliverable is an
*API* other Lumina systems call synchronously, and because a Job cannot return a transformed CSV in
an HTTP response. Worth revisiting if the 3600 s ceiling is ever reached.

**GKE** — full control over runtime, resources, and networking. Rejected as vastly disproportionate:
a cluster to maintain, upgrade, and pay for around the clock, for a service that is idle most of the
time.

**Cloud Functions** — same serverless benefits. Rejected because of tighter memory and execution
limits and a poorer fit for a multi-endpoint API with a shared middleware and auth layer.

**A local or on-prem script** — how the transformation began life. Rejected because the results must
be reachable by other Lumina services and runnable by people who are not the author.
