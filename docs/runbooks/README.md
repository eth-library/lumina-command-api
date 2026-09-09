# Runbooks

One procedure per file, written so someone who did not build the system can execute it.

| # | Procedure | When you need it |
|---|-----------|------------------|
| [01](01-deploy.md) | Deploy to Cloud Run | Shipping a change; rolling back a bad revision |
| [02](02-rotate-secrets.md) | Rotate a secret | Scheduled rotation; suspected key leak; lost laptop |
| [03](03-gcp-project-bootstrap.md) | Bootstrap a GCP project | Standing up a new environment from nothing |
| [04](04-run-udk-pipeline.md) | Run the ETH UDK pipeline end to end | A refreshed UDK export needs processing and indexing |
| [05](05-apigee-proxy.md) | Publish an endpoint through Apigee X | A new backend path prefix needs to reach consumers; a proxy's target, key, or documentation changes |
| [06](06-egress-static-ip.md) | Give the service a static egress IP for reaching Prefect | Standing up or rebuilding the network path to the Lumina Engine; moving the service |

Next number: **07**.

## Rules

- Copy [`TEMPLATE.md`](TEMPLATE.md) to start.
- Every runbook states its **prerequisites** and declares its **variables up front**, so the steps
  below can be pasted without editing each line.
- Every step is copy-pasteable. Placeholders are shell variables, never `<angle brackets>` inside a
  command.
- Every runbook ends with **verification** and **rollback**. If something cannot be rolled back,
  say so explicitly and give the recovery path instead.
- When an operational procedure changes, the runbook changes in the same commit. A runbook that
  describes last quarter's process is worse than no runbook, because it will be followed.
- Every runbook carries a **Last verified** date — set it when you actually run the steps end to
  end. `01`–`04` carry none: they were reconstructed from the code and scripts on 2026-07-31 and
  have not been executed as written. `05` carries one, but it is partial — the date says exactly
  how far the verification went, which is the point of the field.

## Conventions used throughout

| Variable | Value | Notes |
|----------|-------|-------|
| `SERVICE` | `lumina-command-api` | Cloud Run service name, from `deploy.sh` |
| `REGION` | `europe-west6` | Zurich, from `deploy.sh` |
| `PROJECT_ID` | *environment-specific* | `gcloud config get-value project` |

Commands are written for **bash** (Git Bash on Windows, or any POSIX shell). In PowerShell, use
`curl.exe` rather than the `curl` alias, and `$env:VAR = "value"` for variables.
