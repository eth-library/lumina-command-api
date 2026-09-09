# Endpoint — Lumina Engine Datenquelle im Detail

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
| **Pfad** | `/pipeline/sources/{source_id}` |
| **Methode** | GET — **read-only** |
| **Authentifizierung** | `x-api-key` Header — derselbe Schlüssel wie bei `/commands/*` |
| **Content-Type (Response)** | `application/json` |
| **Zweck** | Liefert eine Datenquelle der Lumina Engine mit einer Kennzahl **je Stufe** — inklusive der gemeinsamen Unify-Stufe — und dem Beleg, aus dem jede Zahl stammt |
| **Datenquelle** | Prefect-Server der Lumina Engine, `http://lumina-box01.ethz.ch:4200/api` — nur lesend |
| **Apigee-Proxy** | `lumina-pipeline-sources` (derselbe wie für die Liste; der Pfadrest `/{source_id}` wird durchgereicht), Response-Cache 60 s |
| **Implementierung** | [`app/routers/pipeline.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/pipeline.py) → [`app/services/prefect_status.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/prefect_status.py) |
| **Spezifikation** | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| **Architekturentscheid** | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| **OpenAPI (Portal)** | [lumina-pipeline-sources.yaml](https://github.com/eth-library/lumina-command-api/blob/main/docs/openapi/lumina-pipeline-sources.yaml) |

## Funktion

Die [Übersicht](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources.md) zeigt pro Quelle **eine** Zahl — was der letzte Parse-Lauf geliefert hat.
Dieser Endpoint zeigt für **eine** Quelle, was auf jeder Stufe gemessen wurde, und fügt die
gemeinsame Stufe **`unify`** (`Merge: Sources`) hinzu, weil deren Log ausweist, mit wie vielen
Datensätzen jede Quelle in die Zusammenführung eingeht.

Jede Kennzahl trägt drei Dinge mit sich: den Wert, die **wörtliche Logzeile**, aus der er gelesen
wurde, und die Quellen, für die er gilt. Das ist die Gegenseite eines Prinzips aus
[Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md): eine Zahl ohne Beleg gibt es nicht, und eine Zahl, die nicht ermittelbar ist, wird `null`,
nie `0`.

Er ist **strikt lesend**, wie alle `/pipeline`-Endpoints.

## Pfadparameter

| Parameter | Werte |
|-----------|-------|
| `source_id` | `slsp_eth` · `slsp_network` · `epics` · `erara` · `research_collection` · `semantic_scholar` |

Jeder andere Wert ergibt `404` mit der Liste der gültigen Kennungen.

## Dataflow

```
Client
  │  GET /pipeline/sources/{source_id}        x-api-key: <Key>
  ▼
Router — pipeline.py
  • verify_api_key
  • unbekannte source_id → 404
  ▼
Service — prefect_status.py
  │
  ├─ POST /deployments/filter          alle Deployments, nach Entrypoint indexiert
  │
  ├─ POST /flow_runs/filter   ×3–4     letzter Lauf je Stufe dieser Quelle
  │                                     + letzter Lauf von "Merge: Sources"   ── parallel
  │
  └─ POST /logs/filter        ×2–3     Log jeder Stufe, die je gelaufen ist    ── parallel
  │
  ▼
  Regex je Stufe  →  metrics.records + matched_line
  Regex auf "Merge: Sources"  →  Zeile dieser Quelle  →  unify.metrics
  │
  ▼
JSON: eine Quelle mit stages[], je mit last_run und metrics
```

Rund sieben Requests an Prefect, parallel über wiederverwendete Verbindungen. Die API cacht nicht;
Apigee cacht 60 Sekunden, getrennt je `source_id`.

## Response

```json
{
  "fetched_at": "2026-09-09T14:02:11Z",
  "source": {
    "id": "research_collection",
    "label": "Research Collection",
    "description": "Research Collection XOAI over OAI-PMH → rc_*.",
    "stages": [
      {
        "stage": "harvest",
        "deployment": "Harvester: Research Collection",
        "description": "Research Collection XOAI over OAI-PMH → rc_*.",
        "schedule": null,
        "paused": false,
        "last_run": { "id": "…", "name": "…", "state": "COMPLETED", "…": "…" },
        "metrics": null
      },
      {
        "stage": "parse",
        "deployment": "Parse: RC",
        "description": "XOAI → rc/ready/rc.parquet.",
        "schedule": null,
        "paused": false,
        "last_run": { "id": "…", "name": "…", "state": "COMPLETED", "…": "…" },
        "metrics": {
          "records": 306939,
          "matched_line": "Total records: 306939",
          "covers": ["research_collection"]
        }
      },
      {
        "stage": "unify",
        "deployment": "Merge: Sources",
        "description": "Every ready parquet → merged/unified.parquet, with medium, scope, genre and language normalized to the shared vocabulary.",
        "schedule": null,
        "paused": false,
        "last_run": { "id": "…", "name": "…", "state": "COMPLETED", "…": "…" },
        "metrics": {
          "records": 293374,
          "matched_line": "Loading rc: 293,374 rows in 1 batch(es)...",
          "covers": ["research_collection"]
        }
      }
    ]
  }
}
```

`last_run` hat dieselbe Struktur wie in der Übersicht. Die Quelle selbst trägt hier **kein**
`records`-Feld — die Zahlen stehen an den Stufen.

### Felder in `metrics`

| Feld | Bedeutung |
|------|-----------|
| `records` | Die gemessene Zahl, Integer |
| `matched_line` | Die Logzeile, aus der sie gelesen wurde — **der Beleg**. Wer der Zahl nicht traut, sieht sofort, worauf sie beruht |
| `covers` | Die Quellen, für die die Zahl gilt. Bei quellenspezifischen Stufen die Quelle selbst; bei der Unify-Stufe der beiden SLSP-Quellen **beide** — siehe unten |

`metrics` ist `null`, wenn die Stufe nie gelaufen ist oder keine passende Logzeile enthält.

### Welche Stufen Kennzahlen tragen

| Stufe | `metrics` | Grund |
|-------|-----------|-------|
| `harvest` | immer `null` | Die Harvester schreiben keine auswertbare Zahl ins Log |
| `parse` | Zahl | `Total records: …` bzw. `Parsing … rows` |
| `hierarchy` (nur E-Rara) | immer `null` | Die Zeile `Reconciled hierarchy for 45250 records` wird bewusst nicht ausgewertet — sie zählt Kanten, nicht Bestand |
| `unify` | Zahl | `Loading <key>: … rows` aus `Merge: Sources` |

Belastbar mit Zahlen belegt sind also **nur `parse` und `unify`**. Eine Darstellung, die für jede
Stufe eine Zahl erwartet, wird zwei leere Felder sehen — das ist korrekt.

## Zwei Regeln für die Interpretation

> **Parse- und Unify-Zahl dürfen auseinanderlaufen, und sie tun es.** Im Lauf vom 01.09.2026 hat
> Research Collection **306'939** Datensätze geparst, aber nur **293'374** in die
> Zusammenführung eingebracht. Diese API rechnet die beiden Zahlen bewusst **nicht** gegeneinander
> auf und wählt keine als „die richtige“. Jede Zahl trägt ihre Herkunft; die Interpretation ist
> Sache der Fachstelle.

> **Eine Zahl kann für zwei Quellen gelten — `covers` sagt, für welche.** `Merge: ALMA` führt SLSP
> ETH und SLSP Network zu einem Datensatz pro Werk zusammen, **bevor** die Unify-Stufe zählt. Beide
> Quellen teilen sich deshalb eine Unify-Zahl, die grösser ist als die Parse-Zahl jeder einzelnen.

| Quelle | parse | unify | `covers` |
|---|---:|---:|---|
| `slsp_eth` | 4'427'159 | **20'772'692** | `["slsp_eth", "slsp_network"]` |
| `slsp_network` | 18'632'933 | **20'772'692** | `["slsp_eth", "slsp_network"]` |
| `epics` | 1'085'761 | 1'085'761 | `["epics"]` |
| `erara` | 45'250 | 45'250 | `["erara"]` |
| `research_collection` | 306'939 | 293'374 | `["research_collection"]` |
| `semantic_scholar` | 237'167'341 | 237'167'341 | `["semantic_scholar"]` |

Stand 07.09.2026; die Zahlen ändern sich mit jedem Pipeline-Lauf, die `covers`-Spalte nicht.

**Die Regel für eine Darstellung:** Parse und Unify nur dann als Vorher/Nachher derselben Quelle
gegenüberstellen, wenn `covers` **genau eine** Quelle enthält. Sind es mehrere, gehört die Zahl
diesen Quellen gemeinsam — entsprechend beschriften oder die Gegenüberstellung weglassen. Sonst
zeigt die Darstellung SLSP ETH von 4,4 auf 20,8 Millionen „wachsen“ und dieselben 20,8 Millionen
ein zweites Mal unter SLSP Network.

## Woher die Zahlen kommen

Der Prefect-Server der Lumina Engine speichert **keine Artifacts und keine Task Runs**. Kennzahlen
existieren ausschliesslich als Freitext in den Flow-Run-Logs. Drei Muster werden gelesen, jedes an
einen bestimmten Flow gebunden — dieselbe Phrase kann in einem anderen Flow etwas anderes bedeuten:

| Flow | Erkannte Zeile | Wird zu |
|------|----------------|---------|
| `Parse: *` | `Total records: 4415363` | `parse.metrics` |
| `Parse: Semantic Scholar` | `Parsing 237,167,341 rows in 48 batch(es)...` | `parse.metrics` |
| `Merge: Sources` | `Loading rc: 293,374 rows in 1 batch(es)...` | `unify.metrics` der Quelle `rc` |

**Bewusst nicht gelesen** werden die Zeilen `doi: 566,389 pairs` und `Records kept: 69,604,024`
aus `Deduplicate: Unified`. Ersteres sind Statistiken über Dubletten-Schlüssel, Letzteres die
Menge **nach** der Deduplizierung — beides keine Quellenbestände.

**Was es heute nicht gibt:** die Menge, die von einer Quelle **nach** Projektion und Filter in
`unified.parquet` gelangt. Für Semantic Scholar ist das die entscheidende Zahl — von 237 Millionen
geladenen bleiben nach dem Abstract-Filter rund 49 bis 60 Millionen —, aber `Merge: Sources`
protokolliert sie nicht. Sie wird mit der Stage-Report-Tabelle der Engine kommen
([ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md)), als zusätzliche, optionale Felder in `metrics`.

## Fehlerbehandlung

| Situation | Status | Response |
|-----------|--------|----------|
| `x-api-key` fehlt | 401 | `{"detail": "Missing API key."}` |
| `x-api-key` falsch | 401 | `{"detail": "Invalid API key."}` |
| `INTERNAL_API_KEY` im Container nicht gesetzt | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| Unbekannte `source_id` | 404 | `{"detail": "Unknown source 'x'. Known: slsp_eth, slsp_network, epics, erara, research_collection, semantic_scholar."}` |
| Prefect nicht erreichbar oder Zeitüberschreitung | 502 | `{"detail": "Prefect API unreachable: …"}` |

Das Timeout gegen Prefect beträgt **10 Sekunden pro Request**. Ein `502` betrifft ausschliesslich
`/pipeline/*`; die übrige API bleibt funktionsfähig. Fehlerantworten werden von Apigee nicht gecacht.

## Beispielaufruf

```bash
export API_BASE="https://api.library.ethz.ch/lumina/v1"
export API_KEY="<Apigee Consumer Key>"

curl -sS "$API_BASE/pipeline/sources/research_collection" -H "x-api-key: $API_KEY" \
  | jq -r '.source.stages[] | "\(.stage)\t\(.metrics.records // "—")\t\(.metrics.covers // [] | join(","))\t\(.metrics.matched_line // "")"'
```

Ausgabe, eine Zeile pro Stufe: Stufe, Zahl, `covers`, Beleg.

## Postman-Anleitung

- **Methode:** GET
- **URL (Apigee):** `https://api.library.ethz.ch/lumina/v1/pipeline/sources/research_collection`
- **URL (lokal):** `http://127.0.0.1:8080/pipeline/sources/research_collection`
- **Header:** `x-api-key: <Key>` — über Apigee der Consumer-Key, direkt der interne Key
- **Body:** keiner

Erwartung: `200`, `source.stages` enthält `harvest`, `parse` und `unify`; `parse.metrics` und
`unify.metrics` tragen je eine Zahl mit `matched_line` und `covers`.

Lohnende Varianten: `slsp_eth` und `slsp_network` nacheinander — beide zeigen unter `unify`
dieselbe Zahl mit `covers: ["slsp_eth", "slsp_network"]`. `erara` zeigt als einzige Quelle eine
`hierarchy`-Stufe.

### Negativtests

| Test | Aufruf | Erwartung |
|------|--------|-----------|
| Auth greift | ohne `x-api-key` | `401` |
| Unbekannte Quelle | `/pipeline/sources/gibtsnicht` | `404` mit Liste der gültigen IDs |
| Prefect nicht erreichbar | Dev-Server mit `PREFECT_API_URL=http://127.0.0.1:9/api` starten | `502` innerhalb weniger Sekunden |

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Kennzahlen beruhen auf Log-Parsing** | Wird eine Logmeldung in `lumina-engine` umformuliert, wird aus der Zahl **stillschweigend `null`**. Bewusst so gewählt: lieber keine Zahl als eine falsche. Die dauerhafte Lösung ist [ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md). |
| **Keine Post-Filter-Menge je Quelle** | Was von einer Quelle nach Unify übrig bleibt, steht in keinem Log. Siehe oben. |
| **`harvest` und `hierarchy` ohne Zahl** | Konstruktionsbedingt, kein Fehler. |
| **Unify-Zahl der SLSP-Quellen ist gemeinsam** | `covers` nennt es; eine Darstellung muss es auswerten. |
| **Parse-Zahl und Unify-Zahl können abweichen** | Beide sind korrekt gemessen; sie messen Unterschiedliches. Die API gleicht nichts ab. |
| **`last_run` je Stufe kann aus verschiedenen Pipeline-Läufen stammen** | Prefect verknüpft Läufe nicht. Ist der letzte Unify-Lauf abgestürzt, zeigt `unify.last_run` diesen Absturz, `unify.metrics` aber die Zahlen aus dessen Log — soweit er sie noch geschrieben hat. Die Stufen einer Antwort bilden nicht zwingend **einen** Durchlauf ab. |
| **Prefect ist eine Verfügbarkeitsabhängigkeit** | Bei Störung `502`, die übrige API bleibt gesund. |
| **Kein Cache in der API** | Apigee cacht 60 s je `source_id`. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Alle sechs Quellen auf einen Blick | [Endpoint Datenquellen (Übersicht)](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources.md) |
| Pipeline-Läufe | [Endpoint Pipeline Runs](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-runs.md) |
| Was gebaut wurde und warum, mit Abnahmekriterien | [Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md) |
| Entscheid für eine read-only Fassade | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| Geplante Stage-Report-Tabelle | [ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
