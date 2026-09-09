# Endpoint — Lumina Engine Pipeline-Läufe

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
| **Pfad** | `/pipeline/runs` |
| **Methode** | GET — **read-only** |
| **Authentifizierung** | `x-api-key` Header — derselbe Schlüssel wie bei `/commands/*` |
| **Content-Type (Response)** | `application/json` |
| **Zweck** | Liefert die Flow Runs der Lumina Engine über alle Stufen hinweg, filterbar nach Zustand |
| **Datenquelle** | Prefect-Server der Lumina Engine, `http://lumina-box01.ethz.ch:4200/api` |
| **Implementierung** | [`app/routers/pipeline.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/pipeline.py) → [`app/services/prefect_status.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/prefect_status.py) |
| **Spezifikation** | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| **Architekturentscheid** | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| **Apigee-Proxy** | `lumina-pipeline-runs`, Basepath `/lumina/v1/pipeline/runs`, Response-Cache 60 s |
| **OpenAPI (Portal)** | [lumina-pipeline-runs.yaml](https://github.com/eth-library/lumina-command-api/blob/main/docs/openapi/lumina-pipeline-runs.yaml) |

## Funktion

Der Endpoint liefert eine **flache Liste** der Pipeline-Läufe, neueste zuerst. Jeder Lauf trägt
seinen Zustand, seine Laufzeit und — sofern zuordenbar — die Datenquelle und die Pipeline-Stufe,
zu der er gehört.

Er ist **strikt lesend**. Läufe können über diese API weder gestartet noch abgebrochen werden.

## Input-Parameter (Query)

| Parameter | Typ | Pflicht | Default | Beschreibung |
|-----------|-----|---------|---------|--------------|
| `limit` | Integer | nein | `50` | Anzahl zurückgegebener Läufe, `1`–`200` |
| `state` | Text | nein | alle | Kommaseparierte Prefect-Zustände, z. B. `RUNNING,FAILED` |
| `deployment` | Text | nein | alle | Kommaseparierte Deployment-Namen, exakt wie im Feld `deployment` der Antwort, z. B. `Merge: Sources` |

Gültige Werte für `state`:

```
SCHEDULED  PENDING  RUNNING  COMPLETED  FAILED  CANCELLED  CANCELLING  CRASHED  PAUSED
```

Die Angabe ist unabhängig von Gross- und Kleinschreibung; `running,failed` funktioniert ebenso.

## Response

```json
{
  "fetched_at": "2026-09-06T08:54:09Z",
  "total": 27,
  "runs": [
    {
      "id": "1031e89d-f0ac-44a1-8cb4-b48b705cdb9a",
      "name": "rainbow-octopus",
      "state": "COMPLETED",
      "state_name": "Completed",
      "started_at": "2026-09-06T05:15:01.425777Z",
      "ended_at": "2026-09-06T05:42:03.303476Z",
      "duration_seconds": 1621.877699,
      "run_count": 1,
      "next_scheduled_start_time": null,
      "deployment": "Parse: ALMA ETH",
      "source_id": "slsp_eth",
      "stage": "parse"
    },
    {
      "id": "01a07403-c815-7bdd-84c5-60c3ee6100fb",
      "name": "inventive-griffin",
      "state": "SCHEDULED",
      "state_name": "Scheduled",
      "started_at": null,
      "ended_at": null,
      "duration_seconds": 0.0,
      "run_count": 0,
      "next_scheduled_start_time": "2026-09-27T00:00:00Z",
      "deployment": "DAG Orchestrator",
      "source_id": null,
      "stage": "orchestrate"
    }
  ]
}
```

### Felder

| Feld | Bedeutung |
|------|-----------|
| `total` | Anzahl **aller** Läufe, die dem Filter entsprechen — kann grösser sein als `runs`, wenn `limit` greift |
| `name` | Der von Prefect vergebene Zufallsname des Laufs (`rainbow-octopus`) — die Bezeichnung, unter der er auch in der Prefect-Oberfläche zu finden ist |
| `state` | Zustandstyp, siehe Liste oben |
| `state_name` | Anzeigename desselben Zustands (`Completed`) |
| `started_at` | Startzeit, `null` bei geplanten Läufen |
| `duration_seconds` | Tatsächliche **Ausführungszeit** in Sekunden — läuft mit, solange der Lauf läuft, endgültig nach Abschluss, `0.0` vor dem Start. Nicht die Wanduhr, siehe Hinweis unten |
| `run_count` | Anzahl der Ausführungsversuche — `> 1` bedeutet, dass Prefect wiederholt hat |
| `next_scheduled_start_time` | Bei geplanten Läufen der vorgesehene Startzeitpunkt |
| `deployment` | Name des Prefect-Deployments |
| `source_id` | Zugehörige Datenquelle, oder `null` bei quellenübergreifenden Stufen |
| `stage` | `harvest`, `parse`, `hierarchy`, `merge`, `unify`, `deduplicate`, `load`, `orchestrate` |

### Zuordnung Lauf → Quelle und Stufe

| `stage` | `source_id` | Deployments |
|---------|-------------|-------------|
| `harvest`, `parse` | die jeweilige Quelle | die sechs Harvester und Parser |
| `hierarchy` | `erara` | `Hierarchy: ERARA` |
| `hierarchy` | `null` | `Hierarchy: ALMA` — arbeitet auf dem bereits zusammengeführten ALMA-Bestand |
| `merge` | `null` | `Merge: ALMA` — führt SLSP ETH und SLSP Network zusammen |
| `unify` | `null` | `Merge: Sources` |
| `deduplicate` | `null` | `Deduplicate: Unified` |
| `load` | `null` | `Load: Postgres` — lädt den deduplizierten Bestand nach Cloud SQL |
| `orchestrate` | `null` | `DAG Orchestrator`, `Slim Orchestrator` |

## Dataflow

```
Client
  │  GET /pipeline/runs?state=RUNNING&limit=20
  ▼
Router — pipeline.py
  • verify_api_key
  • state-Liste zerlegen und gegen die gültigen Zustände prüfen
  ▼
Service — prefect_status.py
  │
  ├─ POST /deployments/filter                     für die Zuordnung Lauf → Quelle/Stufe
  │
  ├─ POST /flow_runs/filter   limit, START_TIME_DESC  ── parallel
  └─ POST /flow_runs/count                             ── parallel
  │
  ▼
JSON: runs[] mit source_id und stage angereichert
```

## Fehlerbehandlung

| Situation | Status | Response |
|-----------|--------|----------|
| `x-api-key` fehlt / falsch | 401 | `{"detail": "Missing API key."}` bzw. `Invalid API key.` |
| Unbekannter `state` | 400 | `{"detail": "Unknown state 'BOGUS'. Known: SCHEDULED, PENDING, …"}` |
| Unbekanntes `deployment` | 400 | `{"detail": "Unknown deployment 'Merge: Source'. Known: DAG Orchestrator, …"}` |
| `limit` ausserhalb 1–200 | 400 | `{"detail": "limit must be between 1 and 200, got 999."}` |
| `limit` ist keine Zahl | 422 | FastAPI-Standardantwort der Parametervalidierung |
| Prefect nicht erreichbar | 502 | `{"detail": "Prefect API unreachable: …"}` |

Ein unbekannter Zustand wird **abgewiesen statt ignoriert** — sonst käme auf einen Tippfehler hin
eine plausibel aussehende, aber ungefilterte Liste zurück.

## Beispielaufruf

```bash
export API_BASE="http://127.0.0.1:8080"
export API_KEY="…"

# Was läuft gerade?
curl -sS "$API_BASE/pipeline/runs?state=RUNNING" -H "x-api-key: $API_KEY" \
  | jq -r '.runs[] | "\(.deployment)\t\(.stage)\t\(.duration_seconds | floor)s"'

# Was ist schiefgegangen?
curl -sS "$API_BASE/pipeline/runs?state=FAILED,CRASHED,CANCELLED" -H "x-api-key: $API_KEY" \
  | jq -r '.runs[] | "\(.started_at)\t\(.deployment)\t\(.state)"'

# Letzte abgeschlossene Läufe, ohne die geplanten
curl -sS "$API_BASE/pipeline/runs?state=COMPLETED&limit=10" -H "x-api-key: $API_KEY" \
  | jq -r '.runs[] | "\(.started_at)\t\(.deployment)\t\(.duration_seconds | floor)s"'
```

## Postman-Anleitung

- **Methode:** GET
- **URL (Apigee):** `https://api.library.ethz.ch/lumina/v1/pipeline/runs`
- **URL (lokal):** `http://127.0.0.1:8080/pipeline/runs`
- **URL (Cloud Run, nur für Betrieb):** `https://lumina-command-api-171616207524.europe-west6.run.app/pipeline/runs`
- **Header:** `x-api-key: <Key>`
- **Params:**

| Key | Value | Wirkung |
|-----|-------|---------|
| `limit` | `20` | höchstens 20 Läufe |
| `state` | `RUNNING,FAILED` | nur laufende und fehlgeschlagene |

### Negativtests

| Test | Aufruf | Erwartung |
|------|--------|-----------|
| Auth greift | ohne `x-api-key` | `401` |
| Ungültiger Zustand | `?state=BOGUS` | `400` mit Liste der gültigen Zustände |
| Limit zu gross | `?limit=999` | `400` |
| Limit wird respektiert | `?limit=3` | genau 3 Einträge in `runs` |

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **`duration_seconds` ist Ausführungszeit, nicht Wanduhr** | Der Wert läuft mit, solange der Lauf läuft, und steht still, sobald er den laufenden Zustand verlässt. Pausen zwischen Wiederholungsversuchen zählen nicht mit. Ein in `CANCELLING` hängender Lauf behält den Wert, den er erreicht hatte: am 07.09.2026 meldete `monumental-cuscus` 30'603 s, obwohl er seit 461'863 s feststeckte. **Für «wie lange hängt der Lauf schon» ist `started_at` gegen `fetched_at` zu rechnen, nicht `duration_seconds` zu lesen.** |
| **Geplante Läufe stehen zuoberst** | Sortiert wird absteigend nach `started_at`. Geplante Läufe haben dort `null`, was in der Sortierung zuerst kommt — die Standardabfrage beginnt daher mit den drei künftigen `DAG Orchestrator`-Läufen und nicht mit der jüngsten Aktivität. Für eine Aktivitätsansicht die geplanten Läufe ausschliessen, etwa mit `?state=RUNNING,COMPLETED,FAILED,CRASHED,CANCELLED`. |
| **Läufe lassen sich nicht zu einem Pipeline-Durchlauf gruppieren** | Prefect speichert keine Verknüpfung zwischen einem Orchestrator-Lauf und den Läufen, die er auslöst: `parent_task_run_id` ist bei allen Läufen `null` und Tags werden nicht gesetzt. Eine Gruppierung wäre nur über ein Zeitfenster zu raten und würde falsch gruppieren. |
| **Keine Task-Ebene** | Der Prefect-Server speichert **null** Task Runs. Innerhalb eines Laufs ist kein Fortschritt sichtbar — nur Zustand, Start und Dauer. |
| **Historie erst ab 01.09.2026** | Die Prefect-Metadatenbank wurde am 01.09.2026 um 06:34:02 neu angelegt; frühere Läufe sind dort nicht vorhanden. Das ist **keine** Retention: Prefect 3 OSS löscht keine Flow Runs, die einzige eingestellte Aufbewahrungsfrist betrifft Events (`7 Tage`). Die Liste bleibt daher zunächst kurz und füllt sich mit jedem Wochenlauf. |
| **`stage` und `source_id` sind abgeleitet, nicht von Prefect geliefert** | Beide stammen aus einer Zuordnungstabelle in dieser API. Ein neues Deployment in `lumina-engine` erscheint mit `stage: null`, bis diese API angepasst wird. |
| **Keine Paginierung** | Es gibt nur `limit`, keinen Offset und keinen Cursor. Mehr als 200 Läufe auf einmal sind nicht abrufbar. |
| **Prefect ist eine Verfügbarkeitsabhängigkeit** | Fällt der Prefect-Server oder der Netzwerkweg aus, liefert der Endpoint `502`, während die übrige API gesund ist. |
| **Kein Cache in der API** | Jeder Aufruf liest den aktuellen Stand. Der Response-Cache liegt in Apigee (60 s, getrennt je Query-String); direkte Aufrufe der Cloud-Run-URL umgehen ihn. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Datenquellen statt Läufe | [Endpoint Datenquellen](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources.md) |
| Was gebaut wurde und warum, mit Abnahmekriterien | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| Entscheid für eine read-only Fassade | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| Deployment und Erreichbarkeitsprüfung | [Runbook 01, Schritt 4](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md#verification) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
