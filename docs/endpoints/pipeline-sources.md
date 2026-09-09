# Endpoint — Lumina Engine Datenquellen (Übersicht)

> **Charakter dieses Dokuments:** abgeleitete Endpoint-Dokumentation für Confluence. Keine eigene
> Autorität — massgeblich sind der Code und die
> [ADRs](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr).
> Übergeordnete Dokumentation:
> [System Overview](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md).
>
> **Stand:** 2026-09-09

## Übersicht

| Eigenschaft | Wert |
|-------------|------|
| **Pfad** | `/pipeline/sources` |
| **Methode** | GET — **read-only** |
| **Authentifizierung** | `x-api-key` Header — derselbe Schlüssel wie bei `/commands/*` |
| **Content-Type (Response)** | `application/json` |
| **Zweck** | Liefert die sechs Datenquellen der Lumina Engine mit ihren Pipeline-Stufen, dem letzten Lauf je Stufe und der beim letzten Parse-Lauf beobachteten Bestandszahl |
| **Datenquelle** | Prefect-Server der Lumina Engine, `http://lumina-box01.ethz.ch:4200/api` — nur lesend |
| **Apigee-Proxy** | `lumina-pipeline-sources`, Basepath `/lumina/v1/pipeline/sources`, Response-Cache 60 s |
| **Implementierung** | [`app/routers/pipeline.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/pipeline.py) → [`app/services/prefect_status.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/prefect_status.py) |
| **Spezifikation** | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| **Architekturentscheid** | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| **OpenAPI (Portal)** | [lumina-pipeline-sources.yaml](https://github.com/eth-library/lumina-command-api/blob/main/docs/openapi/lumina-pipeline-sources.yaml) |

## Funktion

Die Lumina Engine führt Metadaten aus sechs Quellsystemen zusammen und orchestriert das mit
Prefect. Prefect kennt dabei nur Flows und Deployments — keinen Begriff «Datenquelle». Dieser
Endpoint übersetzt Prefects Sicht in die Lumina-Begriffe **Quelle**, **Stufe** und **letzter Lauf**
und ist für die Übersichtsdarstellung im Dashboard gedacht: alle sechs Quellen auf einen Blick, je
mit einer Bestandszahl.

Er ist **strikt lesend**. Der Service kennt keinen Codepfad, der etwas in Prefect anlegt, ändert
oder auslöst; Requests an andere als Prefects Lese-Pfade werden bereits im Service abgewiesen.

Kennzahlen **pro Stufe** — inklusive der gemeinsamen Unify-Stufe — liefert der Detail-Endpoint
[`GET /pipeline/sources/{source_id}`](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources-source-id.md).

## Die sechs Quellen

| `source_id` | `label` | Prefect-Deployments (Stufen) |
|-------------|---------|------------------------------|
| `slsp_eth` | SLSP ETH (Alma IZ) | `Harvester: SLSP ETH`, `Parse: ALMA ETH` |
| `slsp_network` | SLSP Network (Alma NZ) | `Harvester: SLSP Network`, `Parse: ALMA Network` |
| `epics` | E-Pics | `Harvester: E PICS`, `Parse: EPICS` |
| `erara` | E-Rara | `Harvester: E RARA`, `Parse: ERARA`, `Hierarchy: ERARA` |
| `research_collection` | Research Collection | `Harvester: Research Collection`, `Parse: RC` |
| `semantic_scholar` | Semantic Scholar | `Harvester: Semantic Scholar`, `Parse: Semantic Scholar` |

Die Zuordnung erfolgt über den **Namen der Python-Funktion** im Prefect-Entrypoint
(`…flows.py:parse_alma_eth`), nicht über den Deployment-Namen. Ein Deployment kann in der
Prefect-Oberfläche umbenannt werden, ohne dass diese API bricht; ein Funktionsname ändert sich nur
mit einer Codeänderung in `lumina-engine`.

## Dataflow

```
Client
  │  GET /pipeline/sources        x-api-key: <Key>
  ▼
Router — pipeline.py
  • verify_api_key (Router-Dependency, identisch zu /commands)
  ▼
Service — prefect_status.py
  │
  ├─ POST /deployments/filter          alle 20 Deployments, nach Entrypoint indexiert
  │
  ├─ POST /flow_runs/filter   ×13      letzter Lauf je Stufe   ── parallel (asyncio.gather)
  │        limit 1, START_TIME_DESC
  │
  └─ POST /logs/filter        ×6       Log des letzten Parse-Laufs ── parallel
           limit 200, TIMESTAMP_ASC
  │
  ▼
  Regex auf die Logzeilen  →  records.count
  │
  ▼
JSON: 6 Quellen mit stages[] und records
```

Pro Aufruf entstehen rund 20 Requests an Prefect, die parallel über **vier wiederverwendete
Keep-Alive-Verbindungen** laufen ([ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md)). Die API selbst cacht nicht — jede
Anfrage liest den aktuellen Stand; Apigee cacht die Antwort 60 Sekunden. Antwortzeit typischerweise
unter einer Sekunde aus Cloud Run.

## Response

```json
{
  "fetched_at": "2026-09-06T08:54:09Z",
  "sources": [
    {
      "id": "erara",
      "label": "E-Rara",
      "description": "e-rara METS over OAI-PMH (set `zut`) → erara_*.",
      "records": {
        "count": 45250,
        "origin": "flow-run-log",
        "flow": "Parse: ERARA",
        "measured_at": "2026-09-06T00:00:33.620826Z"
      },
      "stages": [
        {
          "stage": "harvest",
          "deployment": "Harvester: E RARA",
          "description": "e-rara METS over OAI-PMH (set `zut`) → erara_*.",
          "schedule": null,
          "paused": false,
          "last_run": null
        },
        {
          "stage": "parse",
          "deployment": "Parse: ERARA",
          "description": "METS/MODS → erara/parsed/erara.parquet (hierarchy writes `ready`).",
          "schedule": null,
          "paused": false,
          "last_run": {
            "id": "5a5620ae-ad17-46ef-955b-26b1bb2de87f",
            "name": "competent-weasel",
            "state": "COMPLETED",
            "state_name": "Completed",
            "started_at": "2026-09-06T00:00:07.110239Z",
            "ended_at": "2026-09-06T00:00:33.620826Z",
            "duration_seconds": 26.510587,
            "run_count": 1,
            "next_scheduled_start_time": null
          }
        }
      ]
    }
  ]
}
```

Immer genau sechs Einträge in `sources`, in fester Reihenfolge.

### Felder

| Feld | Bedeutung |
|------|-----------|
| `fetched_at` | Zeitpunkt der Abfrage im Backend. Über Apigee bis zu 60 Sekunden alt |
| `description` | Beschreibungstext **aus dem Prefect-Deployment des Harvesters**, unverändert übernommen — von der Lumina Engine gepflegt, nicht von dieser API, und englisch |
| `records.count` | Bestandszahl aus dem Log des letzten Parse-Laufs, oder `null` |
| `records.origin` | Herkunftsart, derzeit immer `flow-run-log` — die Zahl stammt aus einer Logzeile, nicht aus einer strukturierten Kennzahl |
| `records.flow` | Der Prefect-Flow, dessen Log die Zahl geliefert hat — immer die Parse-Stufe |
| `records.measured_at` | Endzeit dieses Laufs — der Stand, auf den sich die Zahl bezieht |
| `stage` | `harvest`, `parse`, `hierarchy` (nur E-Rara) |
| `schedule` | Liste der Cron-Ausdrücke des Deployments, oder `null`. Die Quellstufen haben keinen eigenen Zeitplan — geplant ist nur der `DAG Orchestrator` (`0 0 * * 0`, sonntags um Mitternacht) |
| `paused` | Ob das Deployment in Prefect pausiert ist |
| `last_run` | Der zuletzt **gestartete** Lauf dieser Stufe, oder `null`, wenn sie noch nie lief |
| `last_run.state` | `COMPLETED`, `RUNNING`, `FAILED`, `CANCELLED`, `CANCELLING`, `CRASHED`, `SCHEDULED`, `PENDING`, `PAUSED` |
| `last_run.duration_seconds` | Tatsächliche Ausführungszeit in Sekunden — nicht die Wanduhr seit `started_at`; Details auf [Endpoint Pipeline Runs](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-runs.md) |
| `last_run.run_count` | Ausführungsversuche; ein Wert über 1 heisst, Prefect hat wiederholt |

> **`records: null` heisst «nicht ermittelbar», nie «null Datensätze».** Eine Darstellung, die
> daraus «0» macht, sagt etwas Falsches.

> **`last_run: null` ist ein Normalzustand, kein Fehler.** Eine Stufe, die auf diesem Prefect-Server
> noch nie gelaufen ist, liefert `null` und HTTP 200. Am 05.09.2026 traf das auf **alle sechs
> Harvester** zu, weil bis dahin nur der `Slim Orchestrator` — die Pipeline ohne Harvest-Schicht —
> ausgeführt worden war. Die Dashboard-Darstellung muss diesen Fall abbilden können.

## Woher die Zahl kommt

Der Prefect-Server der Lumina Engine speichert **keine Artifacts und keine Task Runs**. Es gibt
also keinen strukturierten Ort für Kennzahlen — sie existieren ausschliesslich als Freitext in den
Flow-Run-Logs. Für `records.count` werden zwei Muster gelesen, beide an die Parse-Flows gebunden:

| Flow | Erkannte Zeile |
|------|----------------|
| `Parse: *` | `Total records: 4415363` |
| `Parse: Semantic Scholar` | `Parsing 237,167,341 rows in 48 batch(es)...` |

`records.count` ist damit **immer die Parse-Zahl** — was die Quelle geliefert hat, nicht was nach
der Zusammenführung von ihr übrig ist. Letzteres steht auf der Detail-Seite.

## Fehlerbehandlung

| Situation | Status | Response |
|-----------|--------|----------|
| `x-api-key` fehlt | 401 | `{"detail": "Missing API key."}` |
| `x-api-key` falsch | 401 | `{"detail": "Invalid API key."}` |
| `INTERNAL_API_KEY` im Container nicht gesetzt | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| Prefect nicht erreichbar oder Zeitüberschreitung | 502 | `{"detail": "Prefect API unreachable: …"}` |
| Prefect antwortet mit einem Fehlerstatus | 502 | `{"detail": "Prefect API unreachable: Client error '4xx' …"}` |

Das Timeout gegen Prefect beträgt **10 Sekunden pro Request**. Ein `502` kommt also verlässlich
innerhalb weniger Sekunden — der Client hängt nicht. Fehlerantworten werden von Apigee **nicht**
gecacht.

Ein `502` betrifft **ausschliesslich `/pipeline/*`**. Die übrige API bleibt funktionsfähig, weil
nur diese Endpoints von Prefect abhängen. Für das Dashboard ist das ein eigener Zustand — «Status
der Pipeline derzeit nicht abrufbar» —, kein Fehler von Studio und keiner dieser API.

## Beispielaufruf

```bash
export API_BASE="https://api.library.ethz.ch/lumina/v1"
export API_KEY="<Apigee Consumer Key>"

curl -sS "$API_BASE/pipeline/sources" -H "x-api-key: $API_KEY" \
  | jq -r '.sources[] | "\(.id)\t\(.records.count // "—")\t\(.stages[-1].last_run.state // "nie gelaufen")"'
```

Lokal gegen den Dev-Server stattdessen `API_BASE="http://127.0.0.1:8080"` mit dem internen Key.

## Postman-Anleitung

- **Methode:** GET
- **URL (Apigee):** `https://api.library.ethz.ch/lumina/v1/pipeline/sources`
- **URL (lokal):** `http://127.0.0.1:8080/pipeline/sources`
- **URL (Cloud Run, nur für Betrieb):** `https://lumina-command-api-171616207524.europe-west6.run.app/pipeline/sources`
- **Header:** `x-api-key: <Key>` — über Apigee der Consumer-Key, direkt der interne Key
- **Body:** keiner

Erwartung: `200`, sechs Einträge in `sources`.

### Negativtests

| Test | Aufruf | Erwartung |
|------|--------|-----------|
| Auth greift | `/pipeline/sources` **ohne** `x-api-key` | `401` |
| Prefect nicht erreichbar | Dev-Server mit `PREFECT_API_URL=http://127.0.0.1:9/api` starten | `502` innerhalb weniger Sekunden |
| Cache | Zweiter Aufruf über Apigee innerhalb 60 s | deutlich schneller, identisches `fetched_at` |

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Bestandszahlen beruhen auf Log-Parsing** | Die Zahlen stehen nur als Freitext im Prefect-Log. Wird eine Logmeldung in `lumina-engine` umformuliert, wird aus der Zahl **stillschweigend `null`** — ohne Fehler, ohne Hinweis. Der Ausfallmodus ist bewusst so gewählt: lieber keine Zahl als eine falsche. Die dauerhafte Lösung ist eine Tabelle, die die Engine schreibt ([ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md), in Planung). |
| **`records` bezieht sich auf den letzten Parse-Lauf, nicht auf den Datenbestand** | Die Zahl sagt, was der letzte Lauf verarbeitet hat, nicht wie viele Datensätze heute in MongoDB, im Parquet oder in Cloud SQL liegen. `measured_at` nennt den Stand. |
| **`description` stammt aus Prefect, nicht aus dieser API** | Die Texte sind englisch und werden in `lumina-engine` gepflegt. Ändert sie dort jemand, ändert sich die Anzeige im Dashboard — ohne Deployment dieser API. |
| **Die Quellenliste ist fest verdrahtet** | Eine siebte Quelle in der Lumina Engine erscheint erst, wenn diese API angepasst und deployt wird. |
| **Prefect ist eine Verfügbarkeitsabhängigkeit** | Ist der Prefect-Server oder der Netzwerkweg dorthin gestört, liefert dieser Endpoint `502`, während die übrige API gesund ist. |
| **Historie erst ab 01.09.2026** | Die Prefect-Metadatenbank wurde am 01.09.2026 neu angelegt. Frühere Läufe existieren dort nicht; das ist keine Retention, sondern eine leere Datenbank. |
| **Kein Cache in der API** | Jeder Aufruf erzeugt rund 20 Requests an den Prefect-Server. Der Response-Cache liegt in Apigee (60 s); direkte Aufrufe der Cloud-Run-URL umgehen ihn. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Eine Quelle mit Kennzahlen je Stufe | [Endpoint Datenquelle im Detail](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources-source-id.md) |
| Pipeline-Läufe | [Endpoint Pipeline Runs](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-runs.md) |
| Was gebaut wurde und warum, mit Abnahmekriterien | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| Entscheid für eine read-only Fassade | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| API-Key und Ingress | [ADR 0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md), [ADR 0004](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0004-apigee-as-sole-public-ingress.md) |
| Apigee-Proxy anlegen | [Runbook 05](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/05-apigee-proxy.md) |
| Deployment und Erreichbarkeitsprüfung | [Runbook 01, Schritt 4](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md#verification) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
