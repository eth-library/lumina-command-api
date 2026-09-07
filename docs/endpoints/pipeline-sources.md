# Endpoint — Lumina Engine Datenquellen

> **Charakter dieses Dokuments:** abgeleitete Endpoint-Dokumentation für Confluence. Keine eigene
> Autorität — massgeblich sind der Code und die
> [ADRs](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr).
> Übergeordnete Dokumentation:
> [System Overview](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md).
>
> **Stand:** 2026-09-06

## Übersicht

| Eigenschaft | Wert |
|-------------|------|
| **Pfad (Liste)** | `/pipeline/sources` |
| **Pfad (Detail)** | `/pipeline/sources/{source_id}` |
| **Methode** | GET — **beide read-only** |
| **Authentifizierung** | `x-api-key` Header — derselbe Schlüssel wie bei `/commands/*` |
| **Content-Type (Response)** | `application/json` |
| **Zweck** | Liefert die sechs Datenquellen der Lumina Engine mit ihren Pipeline-Stufen, dem letzten Lauf je Stufe und den beobachteten Bestandszahlen |
| **Datenquelle** | Prefect-Server der Lumina Engine, `http://lumina-box01.ethz.ch:4200/api` |
| **Implementierung** | [`app/routers/pipeline.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/pipeline.py) → [`app/services/prefect_status.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/prefect_status.py) |
| **Spezifikation** | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| **Architekturentscheid** | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |

## Funktion

Die Lumina Engine führt Metadaten aus sechs Quellsystemen zusammen und orchestriert das mit
Prefect. Dieser Endpoint übersetzt Prefects Sicht — 19 Flows und Deployments — in die
Lumina-Begriffe **Quelle**, **Stufe** und **letzter Lauf**.

Er ist **strikt lesend**. Der Service kennt keinen Codepfad, der etwas in Prefect anlegt, ändert
oder auslöst; Requests an andere als Prefects Lese-Pfade werden bereits im Service abgewiesen.

Zwei Ausprägungen:

- **`GET /pipeline/sources`** — alle sechs Quellen mit Stufen, letztem Lauf und einer Bestandszahl
  pro Quelle. Für die Übersichtsdarstellung im Dashboard.
- **`GET /pipeline/sources/{source_id}`** — eine Quelle, zusätzlich mit einem `metrics`-Block **pro
  Stufe** und der gemeinsamen Stufe `unify`. Für die Detailansicht.

## Die sechs Quellen

| `source_id` | `label` | Prefect-Deployments |
|-------------|---------|---------------------|
| `slsp_eth` | SLSP ETH (Alma IZ) | `Harvester: SLSP ETH`, `Parse: ALMA ETH` |
| `slsp_network` | SLSP Network (Alma NZ) | `Harvester: SLSP Network`, `Parse: ALMA Network` |
| `epics` | E-Pics | `Harvester: E PICS`, `Parse: EPICS` |
| `erara` | E-Rara | `Harvester: E RARA`, `Parse: ERARA`, `Hierarchy: ERARA` |
| `research_collection` | Research Collection | `Harvester: Research Collection`, `Parse: RC` |
| `semantic_scholar` | Semantic Scholar | `Harvester: Semantic Scholar`, `Parse: Semantic Scholar` |

Jede Quelle erhält im Detail-Endpoint zusätzlich die gemeinsame Stufe **`unify`**
(`Merge: Sources`), weil deren Log die Zeilenzahl **je Quelle** ausweist.

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
  ├─ POST /deployments/filter          alle 19 Deployments, nach Entrypoint indexiert
  │
  ├─ POST /flow_runs/filter   ×12      letzter Lauf je Stufe   ── parallel (asyncio.gather)
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

Pro Aufruf entstehen rund 19 Requests an Prefect, die parallel laufen. Es gibt **keinen Cache** —
jede Anfrage liest den aktuellen Stand. Antwortzeit typischerweise 1–3 Sekunden.

## Response — `GET /pipeline/sources`

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

### Felder

| Feld | Bedeutung |
|------|-----------|
| `fetched_at` | Zeitpunkt der Abfrage. Es gibt keinen Cache, der Wert ist immer „jetzt“ |
| `description` | Beschreibungstext **aus dem Prefect-Deployment des Harvesters**, unverändert übernommen — von der Lumina Engine gepflegt, nicht von dieser API |
| `records.count` | Bestandszahl aus dem Log des letzten Parse-Laufs, oder `null` |
| `records.origin` | Immer `flow-run-log` — die Zahl stammt aus einer Logzeile, nicht aus einer strukturierten Kennzahl |
| `records.flow` | Der Prefect-Flow, dessen Log die Zahl geliefert hat |
| `records.measured_at` | Endzeit dieses Laufs — der Stand, auf den sich die Zahl bezieht |
| `stage` | `harvest`, `parse`, `hierarchy` (nur E-Rara), im Detail zusätzlich `unify` |
| `schedule` | Liste der Cron-Ausdrücke des Deployments, oder `null`. Die Quellstufen haben keinen eigenen Zeitplan — geplant ist nur der `DAG Orchestrator` (`0 0 * * 0`) |
| `paused` | Ob das Deployment in Prefect pausiert ist |
| `last_run` | Der zuletzt **gestartete** Lauf dieser Stufe, oder `null`, wenn sie noch nie lief |
| `last_run.state` | `COMPLETED`, `RUNNING`, `FAILED`, `CANCELLED`, `CANCELLING`, `CRASHED`, `SCHEDULED`, `PENDING`, `PAUSED` |
| `duration_seconds` | Laufzeit in Sekunden, Fliesskomma |

> **`last_run: null` ist ein Normalzustand, kein Fehler.** Eine Stufe, die auf diesem Prefect-Server
> noch nie gelaufen ist, liefert `null` und HTTP 200. Am 05.09.2026 traf das auf **alle sechs
> Harvester** zu, weil bis dahin nur der `Slim Orchestrator` — die Pipeline ohne Harvest-Schicht —
> ausgeführt worden war. Die Dashboard-Darstellung muss diesen Fall abbilden können.

## Response — `GET /pipeline/sources/{source_id}`

Gleiche Struktur, zusätzlich pro Stufe ein `metrics`-Block und die Stufe `unify`:

```json
{
  "fetched_at": "2026-09-06T08:54:11Z",
  "source": {
    "id": "research_collection",
    "label": "Research Collection",
    "description": "Research Collection XOAI over OAI-PMH → rc_*.",
    "stages": [
      { "stage": "harvest", "deployment": "Harvester: Research Collection",
        "last_run": { "state": "COMPLETED", "...": "..." },
        "metrics": null },
      { "stage": "parse", "deployment": "Parse: RC",
        "last_run": { "state": "COMPLETED", "...": "..." },
        "metrics": { "records": 306939,
                     "matched_line": "Total records: 306939",
                     "covers": ["research_collection"] } },
      { "stage": "unify", "deployment": "Merge: Sources",
        "last_run": { "state": "COMPLETED", "...": "..." },
        "metrics": { "records": 293374,
                     "matched_line": "Loading rc: 293,374 rows in 1 batch(es)...",
                     "covers": ["research_collection"] } }
    ]
  }
}
```

`metrics.matched_line` enthält die Logzeile, aus der die Zahl gelesen wurde. Sie ist der Beleg:
wer der Zahl nicht traut, sieht sofort, worauf sie beruht.

> **Parse- und Unify-Zahl dürfen auseinanderlaufen, und sie tun es.** Im Lauf vom 01.09.2026 hat
> Research Collection **306'939** Datensätze geparst, aber nur **293'374** in die
> Zusammenführung eingebracht. Diese API rechnet die beiden Zahlen bewusst **nicht** gegeneinander
> auf und wählt keine als „die richtige”. Jede Zahl trägt ihre Herkunft; die Interpretation ist
> Sache der Fachstelle.

> **Eine Zahl kann für zwei Quellen gelten — `covers` sagt, für welche.** `Merge: ALMA` führt SLSP
> ETH und SLSP Network zu einem Datensatz pro Werk zusammen, **bevor** die Unify-Stufe zählt. Beide
> Quellen teilen sich deshalb eine Unify-Zahl, die grösser ist als die Parse-Zahl jeder einzelnen:

| Quelle | parse | unify | `covers` |
|---|---:|---:|---|
| `slsp_eth` | 4'427'159 | 20'772'692 | `[“slsp_eth”, “slsp_network”]` |
| `slsp_network` | 18'632'933 | 20'772'692 | `[“slsp_eth”, “slsp_network”]` |
| `epics` | 1'085'761 | 1'085'761 | `[“epics”]` |
| `erara` | 45'250 | 45'250 | `[“erara”]` |
| `research_collection` | 306'939 | 293'374 | `[“research_collection”]` |
| `semantic_scholar` | 237'167'341 | 237'167'341 | `[“semantic_scholar”]` |

Stand 07.09.2026; die Zahlen ändern sich mit jedem Pipeline-Lauf, die `covers`-Spalte nicht. Wer
Parse gegen Unify stellt, muss `covers` auswerten — sonst zeigt die Darstellung SLSP ETH von 4,4
auf 20,8 Millionen „wachsen” und dieselben 20,8 Millionen ein zweites Mal unter SLSP Network.

## Woher die Zahlen kommen

Der Prefect-Server der Lumina Engine speichert **keine Artifacts und keine Task Runs**. Es gibt
also keinen strukturierten Ort für Kennzahlen — sie existieren ausschliesslich als Freitext in den
Flow-Run-Logs. Drei Muster werden gelesen, jedes an einen bestimmten Flow gebunden:

| Flow | Erkannte Zeile |
|------|----------------|
| `Parse: *` | `Total records: 4415363` |
| `Parse: Semantic Scholar` | `Parsing 237,167,341 rows in 48 batch(es)...` |
| `Merge: Sources` | `Loading rc: 293,374 rows in 1 batch(es)...` |

**Bewusst nicht gelesen** werden die Zeilen `doi: 566,389 pairs` und `mmsid: 36,423 pairs` aus
`Deduplicate: Unified`. Das sind Statistiken über Dubletten-Schlüssel, keine Quellenbestände — sie
als Bestandszahl auszuweisen wäre schlicht falsch.

## Fehlerbehandlung

| Situation | Status | Response |
|-----------|--------|----------|
| `x-api-key` fehlt | 401 | `{"detail": "Missing API key."}` |
| `x-api-key` falsch | 401 | `{"detail": "Invalid API key."}` |
| `INTERNAL_API_KEY` im Container nicht gesetzt | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| Unbekannte `source_id` | 404 | `{"detail": "Unknown source 'x'. Known: slsp_eth, slsp_network, epics, erara, research_collection, semantic_scholar."}` |
| Prefect nicht erreichbar oder Zeitüberschreitung | 502 | `{"detail": "Prefect API unreachable: …"}` |
| Prefect antwortet mit einem Fehlerstatus | 502 | `{"detail": "Prefect API unreachable: Client error '4xx' …"}` |

Das Timeout gegen Prefect beträgt **10 Sekunden pro Request**. Ein `502` kommt also verlässlich
innerhalb weniger Sekunden — der Client hängt nicht.

Ein `502` betrifft **ausschliesslich `/pipeline/*`**. Die übrige API bleibt funktionsfähig, weil
nur diese Endpoints von Prefect abhängen.

## Beispielaufruf

```bash
export API_BASE="http://127.0.0.1:8080"
export API_KEY="…"

# Übersicht, kompakt
curl -sS "$API_BASE/pipeline/sources" -H "x-api-key: $API_KEY" \
  | jq -r '.sources[] | "\(.id)\t\(.records.count // "—")\t\(.stages[0].last_run.state // "nie gelaufen")"'

# Eine Quelle im Detail
curl -sS "$API_BASE/pipeline/sources/research_collection" -H "x-api-key: $API_KEY" \
  | jq '.source.stages[] | {stage, records: .metrics.records, beleg: .metrics.matched_line}'
```

## Postman-Anleitung

### Quellen-Übersicht

- **Methode:** GET
- **URL (lokal):** `http://127.0.0.1:8080/pipeline/sources`
- **URL (Cloud Run):** `https://lumina-command-api-171616207524.europe-west6.run.app/pipeline/sources`
- **Header:** `x-api-key: <Key>`
- **Body:** keiner

Erwartung: `200`, sechs Einträge in `sources`.

### Quelle im Detail

- **Methode:** GET
- **URL:** `http://127.0.0.1:8080/pipeline/sources/research_collection`
- **Header:** `x-api-key: <Key>`

Erwartung: `200`, `source.stages` enthält `harvest`, `parse` und `unify`.

### Negativtests

| Test | Aufruf | Erwartung |
|------|--------|-----------|
| Auth greift | `/pipeline/sources` **ohne** `x-api-key` | `401` |
| Unbekannte Quelle | `/pipeline/sources/gibtsnicht` | `404` mit Liste der gültigen IDs |
| Prefect nicht erreichbar | Server mit `PREFECT_API_URL=http://127.0.0.1:9/api` starten | `502` innerhalb weniger Sekunden |

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Bestandszahlen beruhen auf Log-Parsing** | Der Prefect-Server speichert keine Artifacts, die Zahlen stehen nur als Freitext im Log. Wird eine Logmeldung in `lumina-engine` umformuliert, wird aus der Zahl **stillschweigend `null`** — ohne Fehler, ohne Hinweis. Der Ausfallmodus ist bewusst so gewählt: lieber keine Zahl als eine falsche. Die dauerhafte Lösung liegt bei der Engine, die diese Werte als Prefect-Artifacts publizieren sollte. |
| **`records` bezieht sich auf den letzten Parse-Lauf, nicht auf den Datenbestand** | Die Zahl sagt, was der letzte Lauf verarbeitet hat, nicht wie viele Datensätze heute in MongoDB, im Parquet oder in Cloud SQL liegen. `measured_at` nennt den Stand. |
| **Parse-Zahl und Unify-Zahl können abweichen** | Siehe oben, Research Collection. Beide Zahlen sind korrekt gemessen; sie messen Unterschiedliches. |
| **`description` stammt aus Prefect, nicht aus dieser API** | Die Texte sind englisch und werden in `lumina-engine` gepflegt. Ändert sie dort jemand, ändert sich die Anzeige im Dashboard — ohne Deployment dieser API. |
| **Die Quellenliste ist fest verdrahtet** | Eine siebte Quelle in der Lumina Engine erscheint erst, wenn diese API angepasst und deployt wird. |
| **Prefect ist eine Verfügbarkeitsabhängigkeit** | Ist der Prefect-Server oder der Netzwerkweg dorthin gestört, liefern diese Endpoints `502`, während die übrige API gesund ist. |
| **Historie erst ab 01.09.2026** | Die Prefect-Metadatenbank wurde am 01.09.2026 um 06:34:02 neu angelegt. Frühere Läufe existieren dort nicht; das ist keine Retention, sondern eine leere Datenbank. Prefect 3 OSS löscht keine Flow Runs. |
| **Kein Cache** | Jeder Aufruf erzeugt rund 19 Requests an den Prefect-Server. Für ein Dashboard, das häufig aktualisiert, gehört ein Response-Cache in Apigee X, nicht in diese API. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Pipeline-Läufe statt Quellen | [Endpoint Pipeline Runs](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-runs.md) |
| Was gebaut wurde und warum, mit Abnahmekriterien | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| Entscheid für eine read-only Fassade | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| API-Key und Ingress | [ADR 0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md), [ADR 0004](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0004-apigee-as-sole-public-ingress.md) |
| Deployment und Erreichbarkeitsprüfung | [Runbook 01, Schritt 4](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md#verification) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
