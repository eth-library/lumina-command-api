# Endpoint — ETH-UDK Transform JSON

> **Charakter dieses Dokuments:** abgeleitete Endpoint-Dokumentation für Confluence. Keine eigene
> Autorität — massgeblich sind der Code und die
> [ADRs](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr).
> Übergeordnete Dokumentation:
> [System Overview](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md).
>
> **Stand:** 2026-08-02

## Übersicht

| Eigenschaft | Wert |
|-------------|------|
| **Pfad** | `/commands/transform-eth-udk-json` |
| **Methode** | POST |
| **Authentifizierung** | `x-api-key` Header — siehe [System Overview, Abschnitt 6](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| **Content-Type (Request)** | `multipart/form-data` |
| **Content-Type (Response)** | `application/json` |
| **Response-Typ** | `StreamingResponse` |
| **Zweck** | Transformiert und reichert ein ETH-UDK-Dataset an und gibt das Ergebnis als JSON zurück |
| **Implementierung** | [`app/routers/commands.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/commands.py) → [`app/services/transform_eth_udk.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/transform_eth_udk.py) |
| **Runbook** | [04 — Run the ETH UDK pipeline, Schritt 2](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |

## Funktion

Der Endpoint nimmt zwei Dateien als Upload entgegen, führt die ETH-UDK-Transformationspipeline
(Steps 1–7e) aus und gibt das Ergebnis als JSON zurück.

**Input-Parameter** (`multipart/form-data`):

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `source_file` | File | ja | ETH-UDK-Thesaurus-Dataset (`.json` oder `.json.gz`) |
| `rootterms_file` | File | ja | Root-Terms-Lookup (`.json` oder `.json.gz`) |

**Struktur `rootterms_file`:** ein JSON-Objekt, das `sys`-IDs auf eine **Liste** von Root-Term-Einträgen
abbildet. Verwendet wird ausschliesslich der **erste** Eintrag der Liste:

```json
{
  "004123456": [
    { "descriptor_name": "Technik", "category_label": "topical", "root_term": "domain" }
  ]
}
```

**gzip-Erkennung:** die Hilfsfunktion `read_json_file()` dekomprimiert automatisch, wenn eine der
beiden Bedingungen zutrifft:

1. Dateiendung `.gz`
2. HTTP-Header `Content-Encoding: gzip`

Beide Dateien werden mit demselben Header ausgewertet — ein `Content-Encoding: gzip` gilt also für
den gesamten Request, nicht pro Datei.

**Output:** JSON-Array mit den transformierten Records, ausgeliefert als `StreamingResponse`
(`application/json`).

## Dataflow

```
Client
  │  POST multipart/form-data
  │  • source_file    (.json / .json.gz)
  │  • rootterms_file (.json / .json.gz)
  ▼
read_json_file() × 2
  gzip-Dekompression · JSON-Parsing
  → source_data:    list[dict]
  → rootterms_data: dict
  ▼
run_transform_eth_udk()          — Pipeline Steps 1 – 7e
  │
  ├─ VALIDIERUNG
  │    Step 1   Unique Descriptors     Prüft doppelte Sprachen. Nur Logging.
  │    Step 2   Variant Types          Prüft, ob Variants Dictionaries sind. Nur Logging.
  │    Step 3   JSON-Struktur          Validiert udc und Sprachen. ValueError bei Fehler.
  │
  ├─ NORMALISIERUNG
  │    Step 4   Merge Variants         Variants gleicher Sprache via " | " zusammenführen.
  │
  ├─ ANREICHERUNG
  │    Step 5   Broader Term Names     broader_terms-IDs → englische Namen.
  │    Step 6   Related Term Names     related_terms-IDs → englische Namen.
  │
  └─ TRANSFORMATION
       Step 7a  Simplify JSON          Struktur abflachen (descriptor_*, variants_*).
       Step 7b  Add Level              Hierarchie-Ebene via BFS über broader_terms.
       Step 7c  Clean Date             last_transaction_date normalisieren.
       Step 7d  Add Root Terms         sys-IDs gegen rootterms matchen.
       Step 7e  Propagate              Root-Term-Daten via BFS über narrower_terms vererben.
  ▼
data: list[dict]
  ▼
json.dumps(data) → StreamingResponse (application/json)
  ▼
Client
```

**Step 8 (CSV-Export) läuft hier nicht.** Der JSON-Endpoint endet nach Step 7e. Wer CSV benötigt,
verwendet
[`/commands/transform-eth-udk-csv`](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-csv.md).

## Pipeline-Steps im Detail

| Step | Modul | Typ | Beschreibung |
|------|-------|-----|--------------|
| 1 | `step1_check_unique_descriptors` | Validierung | Prüft auf doppelte Sprachen in `descriptors`. Nur Logging, keine Datenänderung. |
| 2 | `step2_check_non_dictionary_variants` | Validierung | Prüft, ob alle `variants`-Einträge Dictionaries sind. Nur Logging, keine Datenänderung. |
| 3 | `step3_validate_json_structure` | Validierung | Prüft: `udc` vorhanden und nicht leer · keine doppelten Descriptor-Sprachen · alle drei Sprachen `ger`/`eng`/`fre` vorhanden. **Bricht bei Fehler mit `ValueError` ab**; die ersten 50 Fehler werden geloggt. |
| 4 | `step4_merge_variants_by_language` | Normalisierung | Fasst mehrere Variants gleicher Sprache zu einem Eintrag zusammen, Separator `" \| "`. Ergebnis nach Sprache sortiert. |
| 5 | `step5_add_broader_terms_names` | Anreicherung | Löst `broader_terms` (sys-IDs) gegen den **englischen** Descriptor-Namen auf. Neues Feld `broader_terms_names`, Separator `" \| "`. Nicht auflösbare IDs werden zu `Unknown (<id>)`. |
| 6 | `step6_add_related_terms_names` | Anreicherung | Wie Step 5, für `related_terms`. Neues Feld `related_terms_names`. |
| 7a | `step7a_simplify_json` | Transformation | Flacht die Struktur ab: `descriptors[]` → `descriptor_ger`/`_eng`/`_fre`, `variants[]` → `variants_ger`/`_eng`/`_fre`. Term-Listen bleiben **Listen**. Baut die Records neu auf — Felder ausserhalb des Zielschemas gehen verloren. |
| 7b | `step7b_add_level` | Transformation | Berechnet `level` via BFS über `broader_terms`. Records ohne `broader_terms` sind Level 0. |
| 7c | `step7c_clean_transaction_date` | Transformation | Entfernt Millisekunden aus `last_transaction_date` → `YYYY-MM-DD HH:MM:SS`. |
| 7d | `step7d_add_cat_root_term` | Anreicherung | Matched `sys`-IDs gegen das Root-Terms-Lookup. Neue Felder `descriptor_name`, `category_label`, `root_term` — **nur bei Treffer**. |
| 7e | `step7e_propagate_root_terms` | Anreicherung | Vererbt die Root-Term-Felder via BFS über `narrower_terms` an alle Nachkommen, die noch keine haben. |

## Output-Schema (JSON)

| Feld | Typ | Immer vorhanden | Beschreibung |
|------|-----|-----------------|--------------|
| `sys` | string | ja | Eindeutige System-ID |
| `udc` | string | ja | UDK-Notation |
| `last_transaction_date` | string | ja | Letzte Änderung (`YYYY-MM-DD HH:MM:SS`) |
| `level` | integer \| null | ja | Hierarchie-Ebene, 0 = Root. `null`, wenn die Ebene nicht auflösbar war |
| `descriptor_ger` | string | nein | Deskriptor Deutsch |
| `descriptor_eng` | string | nein | Deskriptor Englisch |
| `descriptor_fre` | string | nein | Deskriptor Französisch |
| `variants_ger` | string | nein | Varianten Deutsch, `" \| "`-separiert |
| `variants_eng` | string | nein | Varianten Englisch, `" \| "`-separiert |
| `variants_fre` | string | nein | Varianten Französisch, `" \| "`-separiert |
| `broader_terms` | list | ja | Übergeordnete sys-IDs |
| `broader_terms_names` | string | nein | Übergeordnete Namen, `" \| "`-separiert |
| `narrower_terms` | list | ja | Untergeordnete sys-IDs |
| `related_terms` | list | ja | Verwandte sys-IDs |
| `related_terms_names` | string | nein | Verwandte Namen, `" \| "`-separiert |
| `descriptor_name` | string | nein | Root-Term-Deskriptor |
| `category_label` | string | nein | Kategorie-Label |
| `root_term` | string | nein | Root-Term-Bezeichnung |

> **Wichtig für Konsumenten:** die als „nein" markierten Felder fehlen im JSON-Output, wenn sie nicht
> gesetzt werden konnten — sie sind nicht `null`, sondern **nicht vorhanden**. Ein Record ohne
> französischen Deskriptor hat schlicht kein `descriptor_fre`. Der
> [CSV-Endpoint](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-csv.md)
> verhält sich anders: dort erzeugt `csv.DictWriter` für jedes Feld eine Spalte und füllt fehlende
> Werte mit einem leeren String.

Die Sprachfelder sind in der Praxis fast immer gesetzt, weil Step 3 alle drei Sprachen erzwingt und
den Lauf sonst abbricht.

## Fehlerverhalten

| Situation | Status | Antwort |
|-----------|--------|---------|
| `x-api-key` fehlt | 401 | `{"detail": "Missing API key."}` |
| `x-api-key` falsch | 401 | `{"detail": "Invalid API key."}` |
| `INTERNAL_API_KEY` nicht konfiguriert | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| `source_file` oder `rootterms_file` fehlt | 422 | FastAPI-Validierungsfehler |
| Upload ist kein gültiges JSON | 500 | generischer Serverfehler |
| Datei heisst `.gz`, ist aber nicht gzip-komprimiert | 500 | generischer Serverfehler |
| Step 3 lehnt die Struktur ab | 500 | generischer Serverfehler; die konkreten Fehler stehen im Cloud-Run-Log |
| Request grösser als ~32 MB | 413 | von Cloud Run abgewiesen, bevor die Applikation den Request sieht |

> **Hinweis:** Die Transform-Endpoints fangen Pipeline-Fehler nicht ab. Ein `ValueError` aus Step 3
> erreicht FastAPI ungefiltert und wird zu einem generischen `500` — der Client erfährt **nicht**,
> welche Records fehlerhaft sind. Diese Information steht ausschliesslich im Log
> (`gcloud run services logs read lumina-command-api --region europe-west6`). Der Upsert-Endpoint
> behandelt Fehler differenzierter.

## Beispielaufruf

```bash
export API_BASE="https://api.library.ethz.ch/lumina"
export API_KEY="<Apigee Consumer Key>"

gzip -kf udk-export.json rootterms.json

curl -sS -X POST "$API_BASE/commands/transform-eth-udk-json" \
  -H "x-api-key: $API_KEY" \
  -F "source_file=@udk-export.json.gz" \
  -F "rootterms_file=@rootterms.json.gz" \
  -o transformed.json

head -c 400 transformed.json
```

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Kein echtes Streaming** | Die Antwort ist zwar eine `StreamingResponse`, der vollständige Payload wird aber vorher mit `json.dumps()` als String im Speicher aufgebaut (`io.StringIO`). Der Speicherbedarf entspricht dem eines normalen Response — die Instanz muss Quelldaten, transformierte Daten und JSON-String gleichzeitig halten. |
| **Fehler nur im Log** | Siehe Hinweis unter Fehlerverhalten: der Client bekommt bei Strukturfehlern keine verwertbare Meldung. |
| **`level` kann `null` sein** | Records, deren `broader_terms` auf sys-IDs ausserhalb des Datasets zeigen, werden von der BFS nie erreicht und behalten `level: null`. Die Anzahl steht als Warnung im Log. |
| **`last_transaction_date` nur mit Millisekunden parsbar** | Step 7c erwartet exakt `YYYY-MM-DD HH:MM:SS.f`. Ein Datum, das bereits ohne Millisekunden geliefert wird, schlägt beim Parsen fehl und bleibt unverändert — inklusive Warnung im Log. Das Ergebnis ist identisch, die Warnung aber irreführend. |
| **Nur der erste Root-Term zählt** | Step 7d verwendet aus der Liste je `sys`-ID ausschliesslich `rt_list[0]`. Weitere Einträge werden ignoriert. |
| **Request-Limit** | Cloud Run begrenzt den Body auf ~32 MB. Der vollständige UDK-Export überschreitet das unkomprimiert. |
| **Stale Docstring in Step 7a** | Der Docstring behauptet, Term-Listen würden zu kommaseparierten Strings konvertiert. Das passiert erst in Step 8 (CSV). Im JSON-Output sind `broader_terms`, `narrower_terms` und `related_terms` echte Listen. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| Pipeline-Konvention (Step-Module) | [ADR 0002](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0002-numbered-step-modules-pipeline.md) |
| Authentifizierung | [ADR 0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md) |
| gzip und Request-Limit | [ADR 0001](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0001-fastapi-on-cloud-run.md) |
| Vollständiger Ablauf | [Runbook 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md) |
