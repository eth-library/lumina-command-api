# Endpoint — ETH-UDK Transform CSV

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
| **Pfad** | `/commands/transform-eth-udk-csv` |
| **Methode** | POST |
| **Authentifizierung** | `x-api-key` Header — siehe [System Overview, Abschnitt 6](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| **Content-Type (Request)** | `multipart/form-data` |
| **Content-Type (Response)** | `text/csv; charset=utf-8` |
| **Response-Typ** | `StreamingResponse` |
| **Zweck** | Transformiert und reichert ein ETH-UDK-Dataset an und gibt das Ergebnis als CSV zurück |
| **Implementierung** | [`app/routers/commands.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/commands.py) → [`transform_eth_udk.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/transform_eth_udk.py) + [`step8_json_to_csv.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/transformers/eth_udk/step8_json_to_csv.py) |
| **Runbook** | [04 — Run the ETH UDK pipeline, Schritt 2](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |

## Funktion

Dieser Endpoint ist funktional identisch mit dem
[JSON-Endpoint](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-json.md),
durchläuft dieselbe Transformationspipeline (Steps 1–7e) und führt zusätzlich **Step 8** aus, der die
Daten in CSV konvertiert.

**Input-Parameter** (`multipart/form-data`) — identisch mit dem JSON-Endpoint:

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `source_file` | File | ja | ETH-UDK-Thesaurus-Dataset (`.json` oder `.json.gz`) |
| `rootterms_file` | File | ja | Root-Terms-Lookup (`.json` oder `.json.gz`) |

Aufbau des Root-Terms-Lookups, gzip-Erkennung und die Steps 1–7e sind in der
[JSON-Endpoint-Dokumentation](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-json.md)
beschrieben und werden hier nicht wiederholt.

**Output:** CSV als `StreamingResponse` (`text/csv`). Alle Felder werden in Anführungszeichen gesetzt
(`QUOTE_ALL`), Zeilen enden mit `CRLF` (Standarddialekt `excel` des Python-`csv`-Moduls).

## Dataflow

```
Client
  │  POST multipart/form-data
  │  • source_file    (.json / .json.gz)
  │  • rootterms_file (.json / .json.gz)
  ▼
read_json_file() × 2
  gzip-Dekompression · JSON-Parsing
  ▼
run_transform_eth_udk()          — Pipeline Steps 1 – 7e
  identisch mit dem JSON-Endpoint
  ▼
data: list[dict]
  ▼
Step 8 — step8_json_to_csv.transform()
  • fixe Feld-Reihenfolge (18 Spalten)
  • broader_terms / narrower_terms / related_terms → komma-separierte Strings
  • csv.DictWriter mit QUOTE_ALL, Header-Zeile, CRLF
  ▼
csv_content: str
  ▼
StreamingResponse (text/csv)
  ▼
Client
```

Step 8 wird **nicht** vom Orchestrator `run_transform_eth_udk()` aufgerufen, sondern direkt vom
Router. Der Orchestrator endet nach Step 7e.

## CSV-Spaltenreihenfolge

Der CSV-Output enthält die folgenden 18 Spalten in fixer Reihenfolge. Die Reihenfolge steht als
`fieldnames`-Liste in `step8_json_to_csv.py` und ist unabhängig davon, in welcher Reihenfolge die
Felder in den Records entstanden sind.

| # | Spalte | Beschreibung |
|---|--------|--------------|
| 1 | `sys` | System-ID |
| 2 | `level` | Hierarchie-Ebene (leer, wenn nicht auflösbar) |
| 3 | `udc` | UDK-Notation |
| 4 | `last_transaction_date` | Letzte Änderung |
| 5 | `descriptor_eng` | Deskriptor Englisch |
| 6 | `descriptor_ger` | Deskriptor Deutsch |
| 7 | `descriptor_fre` | Deskriptor Französisch |
| 8 | `descriptor_name` | Root-Term-Deskriptor |
| 9 | `category_label` | Kategorie-Label |
| 10 | `root_term` | Root-Term-Bezeichnung |
| 11 | `variants_eng` | Varianten Englisch (`" \| "`-separiert) |
| 12 | `variants_ger` | Varianten Deutsch (`" \| "`-separiert) |
| 13 | `variants_fre` | Varianten Französisch (`" \| "`-separiert) |
| 14 | `broader_terms` | Übergeordnete sys-IDs (komma-separiert) |
| 15 | `broader_terms_names` | Übergeordnete Namen (`" \| "`-separiert) |
| 16 | `narrower_terms` | Untergeordnete sys-IDs (komma-separiert) |
| 17 | `related_terms` | Verwandte sys-IDs (komma-separiert) |
| 18 | `related_terms_names` | Verwandte Namen (`" \| "`-separiert) |

> **Zwei Separatoren im selben Dokument.** Die ID-Spalten (14, 16, 17) verwenden **Komma** — erzeugt
> von `list_to_csv()` in Step 8. Die Namensspalten (11–13, 15, 18) verwenden **`" | "`** — erzeugt
> von den Steps 4, 5 und 6. Das ist Absicht, aber eine häufige Fehlerquelle beim Parsen: die
> Namensfelder dürfen nicht am Komma gesplittet werden, da Deskriptoren selbst Kommata enthalten
> können.

Der Filter des Upsert-Endpoints greift auf die Spalten `category_label` und `root_term` zu — ein CSV
aus diesem Endpoint ist daher direkt als Input für
[`/commands/upsert-pinecone`](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone.md)
verwendbar.

## Unterschied zum JSON-Endpoint

| Aspekt | JSON-Endpoint | CSV-Endpoint |
|--------|---------------|--------------|
| Pipeline | Steps 1–7e | Steps 1–7e **+ Step 8** |
| Listen-Felder | JSON-Arrays (`["1","2","3"]`) | komma-separierte Strings (`"1,2,3"`) |
| Fehlende Felder | Feld **fehlt** im Record | Spalte vorhanden, Wert **leer** |
| `level` nicht auflösbar | `null` | leere Zelle |
| Quoting | — | alle Felder in Anführungszeichen (`QUOTE_ALL`) |
| Zeilenende | — | `CRLF` |
| Media-Type | `application/json` | `text/csv` |
| Typischer Use Case | Weiterverarbeitung in APIs/Services | Export für Excel, Input für den Pinecone-Upsert |

Der Unterschied bei fehlenden Feldern ist der praktisch wichtigste: `csv.DictWriter` schreibt für
jedes Feld der `fieldnames`-Liste eine Spalte und füllt nicht vorhandene Werte mit einem leeren
String. Ein CSV hat also **immer** 18 Spalten pro Zeile, während im JSON-Output je Record
unterschiedliche Felder vorhanden sein können.

## Fehlerverhalten

| Situation | Status | Antwort |
|-----------|--------|---------|
| `x-api-key` fehlt | 401 | `{"detail": "Missing API key."}` |
| `x-api-key` falsch | 401 | `{"detail": "Invalid API key."}` |
| `INTERNAL_API_KEY` nicht konfiguriert | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| `source_file` oder `rootterms_file` fehlt | 422 | FastAPI-Validierungsfehler |
| Upload ist kein gültiges JSON | 500 | generischer Serverfehler |
| Datei heisst `.gz`, ist aber nicht gzip-komprimiert | 500 | generischer Serverfehler |
| Step 3 lehnt die Struktur ab | 500 | generischer Serverfehler; Details nur im Cloud-Run-Log |
| Ein Record enthält ein Feld ausserhalb der 18 `fieldnames` | 500 | `ValueError` aus `csv.DictWriter` — siehe Einschränkungen |
| Request grösser als ~32 MB | 413 | von Cloud Run abgewiesen |

Wie beim JSON-Endpoint fängt der Router Pipeline-Fehler nicht ab; ein `ValueError` wird zu einem
generischen `500` ohne verwertbare Details für den Client.

## Beispielaufruf

```bash
export API_BASE="https://api.library.ethz.ch/lumina"
export API_KEY="<Apigee Consumer Key>"

gzip -kf udk-export.json rootterms.json

curl -sS -X POST "$API_BASE/commands/transform-eth-udk-csv" \
  -H "x-api-key: $API_KEY" \
  -F "source_file=@udk-export.json.gz" \
  -F "rootterms_file=@rootterms.json.gz" \
  -o response.csv

head -1 response.csv
wc -l response.csv
```

Erwartete Kopfzeile:

```
"sys","level","udc","last_transaction_date","descriptor_eng","descriptor_ger","descriptor_fre","descriptor_name","category_label","root_term","variants_eng","variants_ger","variants_fre","broader_terms","broader_terms_names","narrower_terms","related_terms","related_terms_names"
```

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Feldliste ist hart gekoppelt** | `csv.DictWriter` wird ohne `extrasaction="ignore"` verwendet. Fügt ein Pipeline-Step künftig ein Feld hinzu, ohne dass es in die `fieldnames`-Liste von Step 8 aufgenommen wird, bricht der CSV-Export mit `ValueError: dict contains fields not in fieldnames` ab — für **jeden** Request, nicht nur für einzelne Records. Aktuell stimmen die 18 Felder exakt mit dem überein, was die Steps 7a–7e erzeugen. |
| **Kein echtes Streaming** | Das vollständige CSV wird als String im Speicher aufgebaut (`io.StringIO`) und erst dann als `StreamingResponse` ausgeliefert. Die Instanz hält Quelldaten, transformierte Daten und CSV-String gleichzeitig. |
| **Kein BOM** | Die Antwort deklariert `charset=utf-8`, enthält aber kein Byte Order Mark. Excel unter Windows interpretiert die Datei beim Doppelklick je nach Systemgebietsschema falsch — Umlaute und Akzente erscheinen dann zerstört. Abhilfe: Import über *Daten → Aus Text/CSV* mit explizit UTF-8. |
| **Kein Dateiname** | Es wird kein `Content-Disposition`-Header gesetzt. Ein Browser zeigt die Antwort an, statt sie als benannte Datei zu speichern; bei `curl` ist `-o` zwingend. |
| **Fehler nur im Log** | Wie beim JSON-Endpoint: Strukturfehler aus Step 3 ergeben ein generisches `500`. |
| **Request-Limit** | Cloud Run begrenzt den Body auf ~32 MB; der vollständige UDK-Export überschreitet das unkomprimiert. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| JSON-Variante, Pipeline-Steps im Detail, Output-Schema | [Endpoint ETH-UDK Transform JSON](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-json.md) |
| Weiterverarbeitung des CSV | [Endpoint Upsert Pinecone](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone.md) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| Pipeline-Konvention (Step-Module) | [ADR 0002](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0002-numbered-step-modules-pipeline.md) |
| Vollständiger Ablauf | [Runbook 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md) |
