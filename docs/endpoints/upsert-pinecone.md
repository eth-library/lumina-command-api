# Endpoint — ETH-UDK Pinecone Upsert

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
| **Pfad** | `/commands/upsert-pinecone` |
| **Methode** | POST |
| **Authentifizierung** | `x-api-key` Header — siehe [System Overview, Abschnitt 6](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| **Content-Type (Request)** | `multipart/form-data` |
| **Content-Type (Response)** | `application/json` |
| **Response-Typ** | Summary-`dict`, von FastAPI als JSON serialisiert (Fehlerfälle: `JSONResponse`) |
| **Zweck** | Liest eine gzippte CSV-Datei, filtert Records, generiert OpenAI-Embeddings und upsertet Vektoren in einen Pinecone-Index |
| **Verarbeitung** | **synchron** — der Request bleibt bis zum Ende offen. Für grosse Datasets die [Polling-Variante](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone-polling.md) verwenden |
| **Implementierung** | [`app/routers/commands.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/commands.py) → [`app/services/pinecone_upsert.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/pinecone_upsert.py) |
| **Runbook** | [04 — Run the ETH UDK pipeline, Schritt 5](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |

## Funktion

Der Endpoint nimmt eine `.csv.gz`-Datei sowie drei Formular-Parameter entgegen, führt Filterung,
Embedding-Generierung und einen Pinecone-Upsert durch und gibt eine JSON-Zusammenfassung zurück.

### Input-Parameter (`multipart/form-data`)

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `file` | File | ja | **Gzippte** CSV-Datei (`.csv.gz`) mit ETH-UDK-Records |
| `index_name` | Text | ja | Name des Pinecone-Index (z. B. `udk-oa3large3072`) |
| `namespace` | Text | ja | Pinecone-Namespace (z. B. `descriptor_e`) |
| `embedding_fields` | Text | ja | JSON-Array mit CSV-Spaltennamen (z. B. `["descriptor_eng"]` oder `["descriptor_eng", "descriptor_ger"]`) |

Mehrere `embedding_fields` werden **pro Record mit Leerzeichen zu einem Text konkateniert** und
gemeinsam embedded — es entsteht ein Vektor pro Record, nicht einer pro Feld. Leere Werte und `NaN`
werden dabei übersprungen.

### Voraussetzungen

- `OPENAI_API_KEY` und `PINECONE_API_KEY` sind gesetzt — lokal in `.env`, in Cloud Run über den
  Secret Manager ([ADR 0006](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0006-secrets-in-secret-manager.md))
- Der angegebene Pinecone-Index **existiert bereits**. Der Endpoint legt keine Indexe an.
- Die Dimension des Index passt zum Modell (**3072**)
- Die CSV enthält die Spalten `category_label`, `root_term` und `sys` sowie alle in
  `embedding_fields` genannten Spalten
- Die Datei ist **gzip-komprimiert** — siehe Einschränkungen

Ein CSV aus
[`/commands/transform-eth-udk-csv`](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-csv.md)
erfüllt die Spaltenanforderungen bereits.

### Embedding-Modell

`text-embedding-3-large` (3072 Dimensionen), als Modul-Konstante in `pinecone_upsert.py` festgelegt —
nicht per Request wählbar. Pinecone-Environment: `gcp-europe-west4`.

### Output

JSON-Objekt mit einer Zusammenfassung der Verarbeitung:

```json
{
  "total_records": 63391,
  "filtered_records": 12345,
  "embedded_records": 12340,
  "upserted_records": 12340,
  "skipped_records": 5,
  "index_name": "udk-oa3large3072",
  "namespace": "descriptor_e",
  "embedding_fields": ["descriptor_eng"],
  "embedding_model": "text-embedding-3-large",
  "message": "Successfully upserted 12340 vectors to 'udk-oa3large3072/descriptor_e'."
}
```

| Feld | Bedeutung |
|------|-----------|
| `total_records` | Zeilen in der CSV vor dem Filter |
| `filtered_records` | Zeilen nach dem Filter — nur diese werden embedded |
| `embedded_records` | Erfolgreich erzeugte Vektoren |
| `upserted_records` | Nach Pinecone geschriebene Vektoren (identisch mit `embedded_records`) |
| `skipped_records` | Records, deren Embedding-Batch fehlgeschlagen ist — siehe Einschränkungen |

Greift der Filter auf keinen einzigen Record, endet der Lauf **früh und erfolgreich** mit `200` und
einer reduzierten Antwort — kein Fehler:

```json
{
  "total_records": 63391,
  "filtered_records": 0,
  "embedded_records": 0,
  "upserted_records": 0,
  "skipped_records": 0,
  "message": "No records matched the filter criteria."
}
```

Wer den Erfolg eines Laufs automatisiert prüft, muss also `upserted_records` auswerten und darf sich
nicht auf den HTTP-Status verlassen.

## Dataflow

```
Client
  │  POST multipart/form-data
  │  • file (.csv.gz) • index_name • namespace • embedding_fields (JSON-String)
  ▼
Router — commands.py
  • embedding_fields JSON-parsen und Typ prüfen
  • File-Bytes lesen
  • run_pinecone_upsert() in einem Worker-Thread starten (asyncio.to_thread)
  ▼
run_pinecone_upsert()
  │
  ├─ 1  API-Keys prüfen           OPENAI_API_KEY / PINECONE_API_KEY gesetzt?  → ValueError
  ├─ 2  Dekompression             gzip.decompress + pandas.read_csv
  ├─ 3  Filterung                 category_label == 'topical'
  │                               root_term ∈ {'domain', 'facet'}
  │                               → 0 Treffer: früher Ausstieg mit 200
  ├─ 4  Embedding-Felder prüfen   alle Spalten vorhanden?                     → ValueError
  ├─ 5  OpenAI-Client             initialisieren
  ├─ 6  Pinecone-Verbindung       Index in list_indexes() vorhanden?          → ValueError
  ├─ 7  Embeddings                Batches à 100:
  │                                 • embedding_fields pro Record zu einem Text konkatenieren
  │                                 • text-embedding-3-large (3072 dims)
  │                                 • 5 Retries à 5 s bei RateLimit / Netzwerkfehler
  │                                 • 0.5 s Pause zwischen Batches
  │                                 • Vektor: id = sys · values = embedding
  │                                           metadata = alle CSV-Felder + pageContent
  └─ 8  Upsert                    Batches à 50 in index/namespace
  ▼
dict (Zusammenfassung)  →  JSON  →  Client
```

Die Reihenfolge oben entspricht der Nummerierung der Abschnitte im Code. Die Validierung ist damit
**nicht** vollständig vorgezogen: die Prüfung der Embedding-Felder (4) und die Existenz des Index (6)
erfolgen erst **nach** Dekompression und Filterung. Ein falsch geschriebener Indexname kostet also
bereits Parsing-Zeit, aber noch kein OpenAI-Budget — das wird erst ab Schritt 7 ausgegeben.

## Fehlerbehandlung

| Situation | Status | Antwort |
|-----------|--------|---------|
| `x-api-key` fehlt / falsch | 401 | `{"detail": "Missing API key."}` bzw. `"Invalid API key."` |
| `INTERNAL_API_KEY` nicht konfiguriert | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| Pflichtparameter fehlt | 422 | FastAPI-Validierungsfehler |
| `embedding_fields` ist **kein gültiges JSON** | 400 | `{"detail": "embedding_fields must be a valid JSON array, e.g. '[\"descriptor_eng\"]'."}` |
| `embedding_fields` ist gültiges JSON, **aber kein String-Array** | **500** | generischer Serverfehler — siehe Hinweis unten |
| `OPENAI_API_KEY` oder `PINECONE_API_KEY` nicht gesetzt | 400 | `{"detail": "OPENAI_API_KEY is not set in the environment."}` |
| Index existiert nicht | 400 | `{"detail": "Index '…' not found in Pinecone. Available indexes: [...]"}` |
| Embedding-Feld nicht in der CSV | 400 | `{"detail": "Embedding fields not found in CSV columns: [...]. Available columns: [...]"}` |
| Datei ist nicht gzip-komprimiert | 500 | `{"detail": "Not a gzipped file …"}` |
| Spalte `category_label`, `root_term` oder `sys` fehlt | 500 | `{"detail": "'…'"}` (KeyError) |
| OpenAI- oder Pinecone-Ausfall | 500 | `{"detail": "<Fehlertext der Bibliothek>"}` |
| Request grösser als ~32 MB | 413 | von Cloud Run abgewiesen |

> **Abweichung von der Erwartung.** Der Typ-Check für `embedding_fields` wirft ein `ValueError`
> innerhalb eines `try`-Blocks, der ausschliesslich `json.JSONDecodeError` abfängt. Der Fehler läuft
> deshalb ungefiltert bis FastAPI durch und wird zu einem generischen `500` statt zu dem
> beabsichtigten `400`. Betroffen ist nur der Fall „syntaktisch gültiges JSON vom falschen Typ",
> etwa `embedding_fields={"feld":"descriptor_eng"}` oder `embedding_fields=[1,2]`. Ungültiges JSON
> ergibt korrekt `400`. Dasselbe gilt für die
> [Polling-Variante](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone-polling.md).

Im Unterschied zu den Transform-Endpoints gibt dieser Endpoint bei `500` den **Text der
ursprünglichen Exception** an den Client zurück. Das erleichtert die Diagnose, kann aber interne
Details aus den OpenAI- und Pinecone-Bibliotheken nach aussen tragen.

## Beispielaufruf

```bash
export API_BASE="https://api.library.ethz.ch/lumina"
export API_KEY="<Apigee Consumer Key>"

gzip -kf response.csv

curl -sS -X POST "$API_BASE/commands/upsert-pinecone" \
  -H "x-api-key: $API_KEY" \
  -F "file=@response.csv.gz" \
  -F "index_name=udk-oa3large3072" \
  -F "namespace=descriptor_e" \
  -F 'embedding_fields=["descriptor_eng"]'
```

## Laufzeit und Timeouts

Die Verarbeitung ist synchron: der Request bleibt offen, bis alle Embeddings erzeugt und alle
Vektoren geschrieben sind. Bei einem vollständigen UDK-Export (~63 000 Zeilen, nach Filter typisch
gut 12 000 Records) sind das rund 124 OpenAI-Batches — je nach Antwortzeit der API mehrere Minuten
bis über eine Stunde.

| Grenze | Wert | Folge bei Überschreitung |
|--------|------|--------------------------|
| Cloud Run Request-Timeout | **3600 s** (1 h) | Die Instanz bricht ab. Bereits geschriebene Vektoren bleiben in Pinecone, die Antwort geht verloren. |
| Apigee und Client-Timeouts | deutlich kürzer | Der Client bricht ab, **während der Lauf auf Cloud Run weiterläuft** — es entsteht kein Rollback. |

Deshalb ist für vollständige Läufe die
[Polling-Variante](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone-polling.md)
vorgesehen; der synchrone Endpoint eignet sich für kleine Datasets und Tests.

Ein Abbruch ist ungefährlich für die Datenkonsistenz: die Vektor-ID ist die `sys`-ID, ein erneuter
Lauf überschreibt dieselben Vektoren, statt zu duplizieren
([ADR 0003](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0003-openai-embeddings-pinecone-index.md)).
Er kostet allerdings die bereits bezahlten Embeddings erneut.

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Nur gzip** | `run_pinecone_upsert` ruft `gzip.decompress` bedingungslos auf. Eine unkomprimierte `.csv` schlägt mit `500` fehl, obwohl [README.md](https://github.com/eth-library/lumina-command-api/blob/main/README.md) sie als unterstützt beschreibt. Ob Code oder Dokumentation korrigiert wird, ist offen. |
| **Filter ist hart verdrahtet** | `category_label == "topical"` und `root_term ∈ {domain, facet}` stehen im Code, während Index, Namespace und Embedding-Felder Request-Parameter sind. Andere Teilmengen lassen sich nicht über die API auswählen. |
| **Fehlgeschlagene Batches werden still übersprungen** | Nach 5 erfolglosen Retries — oder bei einem `BadRequestError` — liefert der Batch `None` und **alle bis zu 100 Records darin** werden übersprungen. Der Lauf endet trotzdem mit `200`; erkennbar ist das nur an `skipped_records` und an den Logs. Ein anhaltendes Rate-Limit kann so einen grossen Teil des Datasets verlieren, ohne dass der Aufruf fehlschlägt. |
| **Retry nur bei zwei Fehlerklassen** | Wiederholt wird ausschliesslich bei `RateLimitError` und `APIConnectionError`. Andere OpenAI-Fehler brechen den gesamten Lauf mit `500` ab. |
| **Kein Teil-Rollback** | Beim Abbruch nach Schritt 8 bleiben die bereits geschriebenen Batches in Pinecone. Der Lauf ist wiederholbar, aber nicht transaktional. |
| **Alle CSV-Spalten werden Metadaten** | Jede nicht leere Spalte landet als String in den Vektor-Metadaten, dazu `pageContent` mit dem embeddeten Text. Pinecone begrenzt die Metadaten pro Vektor (aktuell 40 KB); der Code prüft das nicht. Bei sehr breiten CSVs kann der Upsert deshalb an Pinecone scheitern. |
| **Request-Limit** | Cloud Run begrenzt den Body auf ~32 MB — auch die komprimierte CSV muss darunter bleiben. |
| **Modell nicht wählbar** | `text-embedding-3-large` ist eine Konstante. Ein Wechsel erfordert eine Code-Änderung und einen Index mit passender Dimension. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Asynchrone Variante mit Fortschritt | [Endpoint Upsert Pinecone Polling](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone-polling.md) |
| Erzeugung der Input-CSV | [Endpoint ETH-UDK Transform CSV](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-csv.md) |
| Embedding- und Index-Entscheid | [ADR 0003](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0003-openai-embeddings-pinecone-index.md) |
| Secrets | [ADR 0006](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0006-secrets-in-secret-manager.md) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| Vollständiger Ablauf | [Runbook 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md) |
