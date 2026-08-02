# Endpoint — ETH-UDK Pinecone Upsert Polling

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
| **Pfad (Start)** | `/commands/upsert-pinecone-polling` |
| **Pfad (Status)** | `/commands/upsert-pinecone-polling/{job_id}/status` |
| **Methode (Start)** | POST |
| **Methode (Status)** | GET |
| **Authentifizierung** | `x-api-key` Header — **für beide Requests**, auch für die Status-Abfrage |
| **Content-Type (Request)** | `multipart/form-data` |
| **Content-Type (Response)** | `application/json` |
| **Zweck** | Asynchrone Variante des Upsert-Endpoints: startet die Verarbeitung als Hintergrundaufgabe und ermöglicht Fortschrittsabfragen via Polling |
| **Implementierung** | [`app/routers/commands.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/routers/commands.py) → [`app/services/pinecone_upsert.py`](https://github.com/eth-library/lumina-command-api/blob/main/app/services/pinecone_upsert.py) |
| **Runbook** | [04 — Run the ETH UDK pipeline, Schritte 5–6](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |

## Funktion

Im Gegensatz zum synchronen Endpoint
[`/commands/upsert-pinecone`](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone.md),
bei dem der Request bis zum Abschluss offen bleibt, arbeitet dieser Endpoint **asynchron mit
Polling**:

1. Der **POST**-Request nimmt Datei und Parameter entgegen, startet die Verarbeitung im Hintergrund
   und gibt sofort eine `job_id` zurück.
2. Der Client fragt anschliessend per **GET** regelmässig den Fortschritt ab (z. B. alle 10 Sekunden).
3. Sobald `status` den Wert `completed` hat, enthält die Antwort das vollständige Ergebnis.

Die interne Verarbeitungslogik — Dekompression, Filterung, Embedding-Generierung, Pinecone-Upsert —
ist **identisch** mit dem synchronen Endpoint. Es wird dieselbe Funktion `run_pinecone_upsert()`
aufgerufen, zusätzlich mit einem `progress`-Dictionary, das sie fortlaufend aktualisiert.

> **Hinweis:** Der Job-Status liegt ausschliesslich im Arbeitsspeicher der Instanz. Bei einem
> Container-Neustart — etwa durch ein neues Deployment — gehen laufende Jobs und deren Status
> verloren. Läuft mehr als eine Instanz, kann eine Status-Abfrage ausserdem auf einer Instanz landen,
> die den Job nicht kennt. Siehe *Bekannte Einschränkungen*.

## POST — Job starten

### Input-Parameter (`multipart/form-data`)

Identisch mit dem synchronen Endpoint:

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `file` | File | ja | **Gzippte** CSV-Datei (`.csv.gz`) mit ETH-UDK-Records |
| `index_name` | Text | ja | Name des Pinecone-Index (z. B. `udk-oa3large3072`) |
| `namespace` | Text | ja | Pinecone-Namespace (z. B. `descriptor_e`) |
| `embedding_fields` | Text | ja | JSON-Array mit CSV-Spaltennamen (z. B. `["descriptor_eng"]`) |

### Response

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "accepted"
}
```

Der Request wird sofort beantwortet (< 1 Sekunde). Die `job_id` ist eine UUID4 und wird für alle
nachfolgenden Status-Abfragen verwendet.

Beachte: zu diesem Zeitpunkt ist **nichts** validiert ausser dem Format von `embedding_fields`. Ob
die API-Keys gesetzt sind, die Datei gzip ist, der Index existiert oder die Spalten stimmen, zeigt
sich erst im Status.

## GET — Fortschritt abfragen

### Pfad

```
GET /commands/upsert-pinecone-polling/{job_id}/status
```

Auch dieser Request benötigt den `x-api-key`-Header — die Authentifizierung hängt am gesamten
`/commands`-Router.

### Response während der Verarbeitung

**Phase: Dekompression und Filterung (0–10 %)**

```json
{
  "status": "processing",
  "phase": "Filtering records",
  "progress_percent": 5
}
```

**Phase: Embedding-Generierung (10–80 %)**

```json
{
  "status": "embedding",
  "phase": "Embedding batch 120/469",
  "progress_percent": 28,
  "filtered_records": 46883,
  "embedded_records": 12000
}
```

**Phase: Pinecone-Upsert (80–98 %)**

```json
{
  "status": "upserting",
  "phase": "Upserting batch 450/938",
  "progress_percent": 89,
  "embedded_records": 46883
}
```

### Response bei Abschluss

```json
{
  "status": "completed",
  "phase": "Done",
  "progress_percent": 100,
  "filtered_records": 46883,
  "embedded_records": 46883,
  "result": {
    "total_records": 63391,
    "filtered_records": 46883,
    "embedded_records": 46878,
    "upserted_records": 46878,
    "skipped_records": 5,
    "index_name": "udk-oa3large3072",
    "namespace": "descriptor_e",
    "embedding_fields": ["descriptor_eng"],
    "embedding_model": "text-embedding-3-large",
    "message": "Successfully upserted 46878 vectors to 'udk-oa3large3072/descriptor_e'."
  }
}
```

Das `result`-Objekt entspricht exakt der Antwort des synchronen Endpoints.

### Response bei Fehler

```json
{
  "status": "failed",
  "phase": "Error",
  "error": "Index 'xyz' not found in Pinecone. Available indexes: ['udk-oa3large3072']"
}
```

Die Felder aus früheren Phasen bleiben erhalten — das Objekt wird fortlaufend ergänzt, nicht ersetzt.
Ein fehlgeschlagener Job behält also `progress_percent` und `phase`-Verlauf bis zum Fehlerzeitpunkt.

### Fortschritts-Skala

| Prozent | Phase |
|---------|-------|
| 0 % | Job akzeptiert, in Warteschlange (`Queued`) |
| 2 % | CSV-Dekompression und Parsing |
| 5 % | Filterung der Records |
| 10–80 % | Embedding-Generierung (proportional zu verarbeiteten Batches) |
| 80–98 % | Pinecone-Upsert (proportional zu verarbeiteten Batches) |
| 100 % | Abgeschlossen |

Zwischen 5 % und 10 % liegen die Prüfung der Embedding-Felder, die Initialisierung des OpenAI-Clients
und der Verbindungsaufbau zu Pinecone. Der Wert springt dort, ohne Zwischenschritte zu melden.

## Fehlerbehandlung

| Situation | Status | Wo sichtbar |
|-----------|--------|-------------|
| `x-api-key` fehlt / falsch | 401 | HTTP-Antwort (beide Requests) |
| Pflichtparameter fehlt | 422 | HTTP-Antwort des POST |
| `embedding_fields` ist **kein gültiges JSON** | 400 | HTTP-Antwort des POST |
| `embedding_fields` ist gültiges JSON, **aber kein String-Array** | **500** | HTTP-Antwort des POST — siehe Hinweis |
| Datei kann nicht gelesen werden | 400 | HTTP-Antwort des POST |
| Unbekannte `job_id` | 404 | `{"detail": "Job '…' not found."}` |
| Fehlende API-Keys, Index nicht gefunden, Spalte fehlt, nicht gzip, OpenAI-/Pinecone-Ausfall | — | **Status-Endpoint** mit `"status": "failed"` und `"error"` |

Fehler während der Hintergrundverarbeitung werden **nicht** als HTTP-Fehler zurückgegeben. Der POST
hat zu diesem Zeitpunkt längst mit `202`-artiger Semantik geantwortet (technisch `200`), und der
Client erfährt das Scheitern ausschliesslich über den Status-Endpoint.

> **Abweichung von der Erwartung.** Wie beim synchronen Endpoint wirft der Typ-Check für
> `embedding_fields` ein `ValueError` in einem `try`-Block, der nur `json.JSONDecodeError` abfängt.
> `embedding_fields={"feld":"x"}` oder `[1,2]` ergibt deshalb ein generisches `500` statt des
> beabsichtigten `400`. Ungültiges JSON ergibt korrekt `400`.

## Voraussetzungen

- `OPENAI_API_KEY` und `PINECONE_API_KEY` sind gesetzt — lokal in `.env`, in Cloud Run über den
  Secret Manager
- Der angegebene Pinecone-Index **existiert bereits** und hat die passende Dimension (**3072**)
- Die CSV enthält die Spalten `category_label`, `root_term` und `sys` sowie alle in
  `embedding_fields` genannten Spalten
- Die Datei ist **gzip-komprimiert**
- Embedding-Modell: `text-embedding-3-large` (3072 Dimensionen), nicht per Request wählbar

## Dataflow

```
Client
  │  POST multipart/form-data
  │  • file (.csv.gz) • index_name • namespace • embedding_fields
  ▼
Router — commands.py
  • embedding_fields JSON-parsen und Typ prüfen
  • File-Bytes lesen
  • job_id = uuid4()
  • _jobs[job_id] = {status: "accepted", phase: "Queued", progress_percent: 0}
  • asyncio.create_task(_run_upsert_job(...))
  │
  ├──────────────► Sofort-Response  { "job_id": …, "status": "accepted" }
  │
  ▼
Background-Task — _run_upsert_job()
  run_pinecone_upsert(..., progress=_jobs[job_id])   in asyncio.to_thread
  │
  │  aktualisiert das Dictionary in-place bei jedem Batch
  ▼
In-Memory Job Store
  _jobs[job_id] = { status, phase, progress_percent,
                    filtered_records, embedded_records, result | error }
  ▲
  │  GET /{job_id}/status   — Client pollt, z. B. alle 10 s
Client
```

Der Job-Store `_jobs` ist ein gewöhnliches Python-Dictionary im Prozessspeicher — keine Datenbank,
kein Redis, keine Persistenz.

## Vergleich: Synchron vs. Polling

| | `/upsert-pinecone` | `/upsert-pinecone-polling` |
|---|---|---|
| **Verhalten** | Request bleibt offen bis Abschluss | Sofortige Antwort, Polling für Status |
| **Timeout-Risiko (HTTP)** | ja — Client, Apigee und Cloud Run (3600 s) | nein für den Request selbst |
| **Risiko, dass der Lauf nicht fertig wird** | nur bei Überschreiten von 3600 s | ja, anderer Grund: CPU-Throttling zwischen den Polls (siehe unten) |
| **Fortschrittsanzeige** | keine | ja (Phase, Prozent, Anzahl Records) |
| **Fehlerbehandlung** | HTTP-Statuscodes (400/500) | `status`-Feld im Polling-Response |
| **Zustand nach Instanz-Neustart** | Request bricht ab, Fehler ist sichtbar | Job verschwindet, Status-Abfrage ergibt `404` |
| **Empfohlen für** | kleine Dateien, schnelle Tests | grosse Dateien, Produktionsbetrieb |

## Postman-Anleitung

### 1. Job starten

- **Methode:** POST
- **URL (lokal):** `http://127.0.0.1:8080/commands/upsert-pinecone-polling`
- **URL (Cloud Run):** `https://lumina-command-api-171616207524.europe-west6.run.app/commands/upsert-pinecone-polling`
- **Header:** `x-api-key: <Key>`
- **Body → form-data:**

| Key | Type | Value |
|-----|------|-------|
| `file` | File | `response.csv.gz` |
| `index_name` | Text | `udk-oa3large3072` |
| `namespace` | Text | `descriptor_e` |
| `embedding_fields` | Text | `["descriptor_eng"]` |

**Response:**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "accepted"
}
```

### 2. Fortschritt abfragen

- **Methode:** GET
- **URL:** `http://127.0.0.1:8080/commands/upsert-pinecone-polling/a1b2c3d4-e5f6-7890-abcd-ef1234567890/status`
- **Header:** `x-api-key: <Key>`

Alle 10 Sekunden wiederholen, bis `"status": "completed"` oder `"failed"` zurückkommt.

Als Shell-Schleife — siehe auch
[Runbook 04, Schritt 6](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps):

```bash
while true; do
  curl -sS "$API_BASE/commands/upsert-pinecone-polling/$JOB_ID/status" \
    -H "x-api-key: $API_KEY" | jq -c '{status, phase, progress_percent}'
  sleep 30
done
```

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **CPU-Throttling nach dem Response** | Cloud Run weist einer Instanz standardmässig nur **während der Bearbeitung eines Requests** CPU zu. `deploy.sh` setzt weder `--no-cpu-throttling` noch `--cpu-boost`. Nachdem der POST beantwortet ist, kann der Hintergrund-Task deshalb stark ausgebremst werden. Regelmässiges Polling mildert das, weil jeder GET wieder CPU freigibt — verlässlich ist es nicht. Wer den Endpoint produktiv nutzt, sollte entweder eng pollen oder die Instanz auf durchgehende CPU-Zuteilung umstellen. |
| **Job-Store nur im Prozessspeicher** | `_jobs` lebt in **einer** Instanz. Bei einem Deployment oder Instanz-Neustart sind laufende Jobs weg. Skaliert Cloud Run auf mehrere Instanzen, kann eine Status-Abfrage auf einer Instanz landen, die den Job nie gesehen hat — die Antwort ist dann `404`, **obwohl der Job läuft**. Ein `404` ist daher kein verlässlicher Beleg dafür, dass der Job gestorben ist; im Zweifel gegen Pinecone verifizieren, statt neu zu starten und die Embeddings ein zweites Mal zu bezahlen. |
| **Job-Store wird nie aufgeräumt** | Abgeschlossene Jobs bleiben samt vollständigem `result` im Dictionary, bis die Instanz endet. Es gibt kein TTL und keine Obergrenze. |
| **Keine Begrenzung paralleler Jobs** | Jeder POST startet einen weiteren Task. Datei-Bytes, DataFrame und Vektoren jedes laufenden Jobs liegen gleichzeitig im Speicher der 8-GiB-Instanz. |
| **Task-Referenz wird nicht gehalten** | Der Rückgabewert von `asyncio.create_task()` wird nicht gespeichert. Python hält auf laufende Tasks nur eine schwache Referenz, ein Task kann daher theoretisch vor Abschluss vom Garbage Collector eingesammelt werden. |
| **Kein Abbruch möglich** | Es gibt keinen Endpoint, um einen laufenden Job zu stoppen. Ein versehentlich gestarteter Lauf über den vollen Datensatz läuft bis zum Ende oder bis die Instanz beendet wird. |
| **Alles Weitere wie beim synchronen Endpoint** | Hart verdrahteter Filter, stilles Überspringen fehlgeschlagener Batches, nur gzip, kein Teil-Rollback, ~32 MB Request-Limit — siehe [Upsert Pinecone](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone.md). |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Synchrone Variante, Verarbeitungsschritte im Detail | [Endpoint Upsert Pinecone](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/upsert-pinecone.md) |
| Erzeugung der Input-CSV | [Endpoint ETH-UDK Transform CSV](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/transform-eth-udk-csv.md) |
| Embedding- und Index-Entscheid | [ADR 0003](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0003-openai-embeddings-pinecone-index.md) |
| Cloud-Run-Dimensionierung und Timeouts | [ADR 0001](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0001-fastapi-on-cloud-run.md) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
| Vollständiger Ablauf | [Runbook 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md) |
