# Endpoint documentation

Derived, Confluence-facing reference pages — one per endpoint, written in German for that
audience. They have **no authority**: the code and the [ADRs](../adr/) are the source of truth, and
these pages are created or updated **only when asked**, never as a step in the loop.

Links inside these pages are absolute `github.com` URLs so they still resolve after the content is
pasted into Confluence.

| Endpoint | Seite |
|----------|-------|
| `POST /commands/transform-eth-udk-json` | [transform-eth-udk-json.md](transform-eth-udk-json.md) |
| `POST /commands/transform-eth-udk-csv` | [transform-eth-udk-csv.md](transform-eth-udk-csv.md) |
| `POST /commands/upsert-pinecone` | [upsert-pinecone.md](upsert-pinecone.md) |
| `POST /commands/upsert-pinecone-polling`<br>`GET /commands/upsert-pinecone-polling/{job_id}/status` | [upsert-pinecone-polling.md](upsert-pinecone-polling.md) |
| `GET /pipeline/sources` | [pipeline-sources.md](pipeline-sources.md) |
| `GET /pipeline/sources/{source_id}` | [pipeline-sources-source-id.md](pipeline-sources-source-id.md) |
| `GET /pipeline/runs` | [pipeline-runs.md](pipeline-runs.md) |

The utility endpoints (`/`, `/health`, `/version`) have no page of their own — they are covered in
[SYSTEMOVERVIEW.md](../SYSTEMOVERVIEW.md), Abschnitt 4.

## Struktur einer Seite

Übersicht · Funktion · Dataflow · endpointspezifische Abschnitte · Fehlerbehandlung ·
Beispielaufruf · Bekannte Einschränkungen · Verwandte Dokumentation.

`Bekannte Einschränkungen` ist Teil der Seite, nicht ein Anhang: das Verhalten, das dort steht,
ist beim Aufruf des Endpoints beobachtbar, und ohne diesen Abschnitt liest sich die Seite
verlässlicher, als der Endpoint ist.

## Rules

- One page per endpoint, filename matching the endpoint path.
- Add a row to the table above when a page is added — an endpoint page nobody can find is not
  documentation.
- Links to other repository files use absolute `github.com/eth-library/lumina-command-api/blob/main/…`
  URLs, not relative paths, so the Confluence copy stays usable.
- When an endpoint's behaviour changes, the page changes with it. These pages describe what the
  endpoint does **now**.
