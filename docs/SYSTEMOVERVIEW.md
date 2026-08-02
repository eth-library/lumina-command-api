# Lumina Command API — System Overview

> **Charakter dieses Dokuments:** abgeleitete Zusammenfassung für die interne Confluence-Dokumentation.
> Es hat **keine eigene Autorität** — massgeblich sind die [ADRs](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr), die [Specs](https://github.com/eth-library/lumina-command-api/tree/main/docs/specs), die
> [Runbooks](https://github.com/eth-library/lumina-command-api/tree/main/docs/runbooks) und der Code. Bei Widerspruch gewinnt die Quelle; dieses Dokument wird
> korrigiert. Es wird **auf Anforderung** erstellt und aktualisiert, nicht als Schritt im
> Entwicklungsablauf.
>
> **Stand:** 2026-08-02

---

## Key Facts

| | |
|---|---|
| **Funktionsbereich** | Lumina Control |
| **Tech-Stack** | FastAPI (Python 3.10+) |
| **Google-Projekt** | `ethbib-lumina` (ETHBIB-LUMINA), Projektnummer `171616207524` |
| **Cloud Run Service** | `lumina-command-api`, Region `europe-west6` (Zürich) |
| **Fixe Outbound-IP** | `34.65.28.93` — für Allow-Listing bei Zielsystemen |
| **Runtime Service Account** | `171616207524-compute@developer.gserviceaccount.com` |
| **API intern (Cloud Run)** | `https://lumina-command-api-171616207524.europe-west6.run.app/` |
| **API extern (Apigee)** | `api.library.ethz.ch/lumina/` — siehe Lumina Dev Portal & API Gateway |
| **Swagger UI** | `/docs` am jeweiligen Host |
| **Repository** | https://github.com/eth-library/lumina-command-api |

---

## 1. Zweck und Hauptaufgaben

Die Lumina Command API trennt **Benutzerinteraktion** und **technische Ausführung**. Sie stellt eine
kontrollierte interne Schnittstelle bereit, über die Lumina Studio Aktionen auslösen kann, ohne direkt
auf technische Backend-Prozesse zugreifen zu müssen.

- Bereitstellung interner API-Endpunkte
- Entgegennahme von Kommandos aus Lumina Studio
- Auslösen technischer Aktionen
- Vermittlung zwischen Studio, Workflows, Core und Experience-Komponenten
- Kontrollierte Ausführung definierter Systemfunktionen

Innerhalb der **Lumina-Initiative** der ETH-Bibliothek ermöglicht der Service:

- Data Readiness für AI-basiertes Discovery
- Metadaten-Anreicherung und -Normalisierung
- Transformationspipelines für nachgelagerte Systeme
- Embedding-Generierung und Vektor-Datenbank-Upserts
- Verarbeitung grosser Datenmengen via Streaming und asynchrone Background-Tasks

## 2. Interaktionen mit anderen Komponenten

| Quelle / Ziel | Interaktion |
|---------------|-------------|
| Lumina Studio Dashboard | empfängt Kommandos und Aktionen |
| Lumina CMS | kann Publikations- oder Verwaltungsaktionen entgegennehmen |
| Lumina Workflows | startet oder steuert Workflows |
| Lumina Core DB | liest oder aktualisiert Daten |
| Lumina Search Index | kann Indexierungsprozesse auslösen |

Die Gegenstellen dieser Interaktionen liegen in den jeweiligen Lumina-Komponenten und damit in
eigenen Codebasen; in diesem Repository ist nur die Seite der Command API sichtbar.

---

## 3. Architektur

### 3.1 Request-Pfad

Externe Konsumenten erreichen die API **ausschliesslich über Apigee X**. Die Cloud-Run-URL ist ein
Implementierungsdetail und wird Konsumenten nicht publiziert ([ADR 0004](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0004-apigee-as-sole-public-ingress.md)).

```
Client (Postman / Swagger UI / Studio)
        │
        │  x-api-key: <Apigee Consumer Key>
        ▼
┌────────────────────────────────────┐
│  Apigee X — api.library.ethz.ch    │
│  • Consumer-API-Key-Verifikation   │
│  • CORS-Handling (Preflight)       │
│  • Injektion des internen API-Keys │
└──────────────┬─────────────────────┘
               │  x-api-key: <Internal API Key>
               ▼
┌────────────────────────────────────┐
│  Lumina Command API                │
│  FastAPI auf Google Cloud Run      │
└──────────────┬─────────────────────┘
               │
               ▼
   Streaming Response (JSON / CSV)  ·  Pinecone (Vektoren)
```

**Apigee besitzt die Consumer-Identität** (Keys werden dort ausgestellt, skopiert und widerrufen) und
**Apigee besitzt CORS** — die FastAPI-Applikation registriert bewusst **keine** CORS-Middleware. Der
Cloud-Run-Dienst bleibt auf Plattformebene `--allow-unauthenticated` und erzwingt den internen Key im
Applikationscode.

### 3.2 Schichtenmodell

Die Applikation folgt einer klaren Schichtenarchitektur mit Separation of Concerns:

```
┌──────────────────────────────────────────────────────┐
│  FastAPI Application — app/main.py                    │
│  Utility-Endpoints, Router-Registrierung, Logging     │
├──────────────────────────────────────────────────────┤
│  Authentication Layer — app/auth.py                   │
│  • x-api-key Header-Validierung                       │
│  • nur für /commands/* (Router-Dependency)            │
├──────────────────────────────────────────────────────┤
│  Router Layer — app/routers/commands.py               │
│  • File-Upload & Dekompression (gzip)                 │
│  • Endpoint-Routing                                   │
│  • Streaming Response                                 │
│  • Async Job Management (Polling)                     │
├──────────────────────────────────────────────────────┤
│  Service Layer                                        │
│  app/services/transform_eth_udk.py                    │
│  app/services/pinecone_upsert.py                      │
│  • Pipeline-Orchestrierung                            │
│  • Embedding-Generierung (OpenAI)                     │
│  • Vektor-Upsert (Pinecone)                           │
│  • Error Handling & Logging                           │
├──────────────────────────────────────────────────────┤
│  Transformer Layer — app/transformers/eth_udk/        │
│  • Step 1–3:   Validierung                            │
│  • Step 4–6:   Normalisierung & Anreicherung          │
│  • Step 7a–7e: Transformation & Enrichment            │
│  • Step 8:     CSV-Konvertierung                      │
└──────────────────────────────────────────────────────┘
```

### 3.3 Design-Prinzipien

| Prinzip | Beschreibung |
|---------|--------------|
| Stateless | Kein persistenter Storage — vollständige In-Memory-Verarbeitung |
| Modulare Pipeline | Jeder Transformationsschritt ist ein eigenständiges Modul mit einheitlicher Signatur |
| Pipeline-Kompatibilität | Alle Steps akzeptieren `list[dict]` und geben `list[dict]` zurück |
| Stabile Step-Nummern | Neue Schritte werden mit Buchstabensuffix eingefügt (`7a`–`7e`) statt umnummeriert |
| gzip-Unterstützung | Uploads als `.json.gz` / `.csv.gz` (Workaround für das ~32 MB Request-Limit von Cloud Run) |
| Streaming Response | Grosse Ergebnisse werden als `StreamingResponse` zurückgegeben |
| Async Background-Tasks | Langlebige Operationen (Embedding-Generierung) laufen als Polling-basierte Hintergrundaufgaben |
| Strukturiertes Logging | Jeder Pipeline-Step loggt Status, Statistiken und Warnungen |

Details und Begründung: [ADR 0002 — Numbered step modules](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0002-numbered-step-modules-pipeline.md).

---

## 4. API-Oberfläche

### Utility-Endpoints (ohne Authentifizierung)

| Pfad | Methode | Beschreibung |
|------|---------|--------------|
| `/` | GET | Service-Name und Umgebung |
| `/health` | GET | Health-Check (`{"status": "ok"}`) |
| `/version` | GET | Name, Version und Umgebung |

Sie bleiben bewusst ungeschützt, damit Cloud-Run-Health-Checks und Uptime-Monitoring ohne Credential
funktionieren.

### Command-Endpoints (erfordern `x-api-key`)

| Pfad | Methode | Beschreibung | Runbook |
|------|---------|--------------|---------|
| `/commands/transform-eth-udk-json` | POST | ETH-UDK-Datensatz transformieren → JSON | [04, Schritt 2](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |
| `/commands/transform-eth-udk-csv` | POST | ETH-UDK-Datensatz transformieren → CSV | [04, Schritt 2](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |
| `/commands/upsert-pinecone` | POST | Embedding-Generierung und Upsert nach Pinecone (synchron) | [04, Schritt 5](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |
| `/commands/upsert-pinecone-polling` | POST | Asynchronen Upsert-Job starten, gibt `job_id` zurück | [04, Schritt 5](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |
| `/commands/upsert-pinecone-polling/{job_id}/status` | GET | Status eines Upsert-Jobs abfragen | [04, Schritt 6](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md#steps) |

Der vollständige Ablauf über alle fünf Kommandos — vom komprimierten Export bis zum verifizierten
Pinecone-Namespace — steht in
[Runbook 04 — Run the ETH UDK pipeline end to end](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md).
Alle Runbooks: [github.com/eth-library/lumina-command-api/docs/runbooks](https://github.com/eth-library/lumina-command-api/tree/main/docs/runbooks).

### Eingabeformate

**Transform-Endpoints** (`multipart/form-data`):

| Key | Typ | Beschreibung |
|-----|-----|--------------|
| `source_file` | File | ETH-UDK-Datensatz (`.json` oder `.json.gz`) |
| `rootterms_file` | File | Root-Terms-Lookup (`.json` oder `.json.gz`) |

**Upsert-Endpoints** (`multipart/form-data`):

| Key | Typ | Beschreibung |
|-----|-----|--------------|
| `file` | File | CSV-Datei (`.csv.gz` — siehe Einschränkung in Abschnitt 10) |
| `index_name` | string | Ziel-Index in Pinecone |
| `namespace` | string | Ziel-Namespace in Pinecone |
| `embedding_fields` | string | JSON-Array der zu embeddenden Felder, z. B. `'["descriptor_eng"]'` |

### Grosse Dateien

Cloud Run begrenzt Request-Bodies auf **~32 MB**. Deshalb werden gzip-komprimierte Uploads
unterstützt und empfohlen — erkannt am Dateisuffix `.gz` oder am Header `Content-Encoding: gzip`.

---

## 5. Fachliche Abläufe

### 5.1 ETH-UDK-Transformationspipeline

Orchestriert in `app/services/transform_eth_udk.py`. Die Aufrufreihenfolge in dieser Datei ist die
einzige Definition der Pipeline-Reihenfolge.

| Step | Modul | Wirkung |
|------|-------|---------|
| 1 | `step1_check_unique_descriptors` | Validierung — warnt, verändert die Daten nicht |
| 2 | `step2_check_non_dictionary_variants` | Validierung — warnt, verändert die Daten nicht |
| 3 | `step3_validate_json_structure` | Validierung — bricht den Lauf bei Strukturfehlern mit `ValueError` ab |
| 4 | `step4_merge_variants_by_language` | Normalisierung — Varianten je Sprache zusammenführen |
| 5 | `step5_add_broader_terms_names` | Anreicherung — Namen der Oberbegriffe ergänzen |
| 6 | `step6_add_related_terms_names` | Anreicherung — Namen verwandter Begriffe ergänzen |
| 7a | `step7a_simplify_json` | Struktur vereinfachen |
| 7b | `step7b_add_level` | Hierarchieebene ergänzen |
| 7c | `step7c_clean_transaction_date` | Transaktionsdatum bereinigen |
| 7d | `step7d_add_cat_root_term` | Kategorie und Root-Term ergänzen — **benötigt `rootterms_file`** |
| 7e | `step7e_propagate_root_terms` | Root-Terms in der Hierarchie propagieren |
| 8 | `step8_json_to_csv` | JSON → CSV |

**Step 8 ist nicht Teil von `run_transform_eth_udk`.** Der Orchestrator endet nach 7e; Step 8 wird
direkt vom CSV-Endpoint im Router aufgerufen. Der JSON-Endpoint liefert das Ergebnis nach 7e.

### 5.2 Embedding und Pinecone-Upsert

Implementiert in `app/services/pinecone_upsert.py` ([ADR 0003](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0003-openai-embeddings-pinecone-index.md)).

1. **API-Keys prüfen** — fehlende Keys führen zu `400` mit klarer Meldung.
2. **CSV dekomprimieren und parsen** (Pandas).
3. **Filtern** auf `category_label == "topical"` **und** `root_term ∈ {domain, facet}`. Dieser Filter
   ist im Code fest verdrahtet (siehe Abschnitt 10).
4. **Embedding-Felder prüfen** — nicht vorhandene Spalten führen zu `400` samt Liste der verfügbaren Spalten.
5. **Embeddings erzeugen** — Modell `text-embedding-3-large`, Batches à 100, 0.5 s Pause zwischen
   Batches, 5 Retries mit 5 s Wartezeit bei Rate-Limit- und Verbindungsfehlern. Ein Batch mit
   `BadRequestError` wird übersprungen und gezählt, nicht als Fehler behandelt.
6. **Upsert nach Pinecone** — Batches à 50, Environment `gcp-europe-west4`, Index und Namespace als
   Request-Parameter.

Konventionen: Die **Vektor-ID ist das Feld `sys`** (ETH-UDK-Identifikator), ein erneuter Lauf
überschreibt also, statt zu duplizieren. **Alle CSV-Spalten** werden als Metadaten mitgegeben, plus
das Feld `pageContent` mit dem exakt embeddeten Text.

Rückgabe ist eine Zusammenfassung mit `total_records`, `filtered_records`, `embedded_records`,
`upserted_records`, `skipped_records`, Index, Namespace, Feldern und Modell.

### 5.3 Polling-Variante

`/commands/upsert-pinecone-polling` legt einen Job mit UUID an, startet die Verarbeitung als
`asyncio`-Task und antwortet sofort mit `{"job_id": ..., "status": "accepted"}`. Der Status-Endpoint
liefert den fortlaufend aktualisierten Fortschritt:

| Feld | Beispiel |
|------|----------|
| `status` | `accepted` · `starting` · `processing` · `embedding` · `upserting` · `completed` · `failed` |
| `phase` | `Embedding batch 3/47` |
| `progress_percent` | `10` → `80` (Embedding), `80` → `98` (Upsert), `100` (fertig) |
| `result` | Zusammenfassung wie oben, sobald `completed` |
| `error` | Fehlertext, falls `failed` |

Der Job-Store ist ein **In-Memory-Dictionary** — mit den Folgen aus Abschnitt 10.

---

## 6. Sicherheit

### API-Key-Authentifizierung

Alle `/commands/*`-Endpoints sind durch eine interne API-Key-Prüfung abgesichert (`app/auth.py`). Der
Key wird über den Header `x-api-key` übergeben und gegen die Umgebungsvariable `INTERNAL_API_KEY`
validiert ([ADR 0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md)).

| Szenario | HTTP-Status | Antwort |
|----------|-------------|---------|
| Header fehlt | 401 | `{"detail": "Missing API key."}` |
| Falscher Key | 401 | `{"detail": "Invalid API key."}` |
| Key nicht konfiguriert | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| Korrekter Key | — | Request wird verarbeitet |

Die Prüfung hängt als FastAPI-Dependency **am Router**, nicht an den einzelnen Endpoints:

```python
router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(verify_api_key)])
```

Damit ist jeder künftige Command-Endpoint automatisch geschützt. Die Utility-Endpoints (`/`,
`/health`, `/version`) sind bewusst nicht geschützt. Der `500` bei fehlender Konfiguration ist
Absicht: ein fehlkonfiguriertes Deployment soll laut scheitern, statt jeden Request anzunehmen.

Im Produktionsbetrieb injiziert Apigee den internen Key automatisch — externe Konsumenten verwenden
ausschliesslich ihren Apigee Consumer Key und sehen den internen Key nie.

### Secret Management

Drei Secrets liegen im **Google Cloud Secret Manager** ([ADR 0006](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0006-secrets-in-secret-manager.md)):

| Secret | Beschreibung |
|--------|--------------|
| `OPENAI_API_KEY` | API-Key für die OpenAI-Embedding-Generierung |
| `PINECONE_API_KEY` | API-Key für die Pinecone-Vektordatenbank |
| `INTERNAL_API_KEY` | Interner API-Key zur Absicherung der `/commands/*`-Endpoints |

- **Lokal:** Werte kommen aus `.env` (via `python-dotenv`). `.env` steht in `.gitignore` und wird
  **nie** committet; `.env.example` ist die committete Vorlage.
- **Cloud Run:** Cloud Run liest keine `.env`-Dateien. `deploy.sh` referenziert die Secrets über
  `--set-secrets=NAME=SECRET_NAME:latest`; sie werden als Umgebungsvariablen in den Container
  injiziert und von `Config` in `app/config.py` über `os.getenv()` gelesen — **derselbe Codepfad wie
  lokal**, ohne Fallunterscheidung.
- `setup-secrets.sh` liest die drei Keys aus der lokalen `.env`, legt fehlende Secrets an
  (`--replication-policy=automatic`) und lädt den aktuellen Wert als neue Version hoch.
- Der Runtime Service Account benötigt einmalig projektweit `roles/secretmanager.secretAccessor`.

**Prozeduren** — Rotation, Bootstrap und Deployment sind in den Runbooks beschrieben und dort
massgeblich; dieses Dokument wiederholt sie bewusst nicht:

- [Runbook 01 — Deploy to Cloud Run](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md)
- [Runbook 02 — Rotate a secret](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/02-rotate-secrets.md)
- [Runbook 03 — Bootstrap a GCP project](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/03-gcp-project-bootstrap.md)
- [Runbook 04 — Run the ETH UDK pipeline end to end](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md)

---

## 7. Betrieb und Deployment

### Zielplattform

| Parameter | Wert |
|-----------|------|
| Plattform | Google Cloud Run |
| Projekt | `ethbib-lumina` (ETHBIB-LUMINA) |
| Region | `europe-west6` (Zürich) |
| Zugriff | öffentlich (`--allow-unauthenticated`), abgesichert durch internen API-Key und Apigee als Gateway |
| Timeout | 3600 Sekunden (1 Stunde) |
| Memory | 8 GiB |
| CPU | 4 vCPU |
| Fixe Outbound-IP | `34.65.28.93` |

Die Dimensionierung ist auf den Lauf über den **vollständigen Datensatz in einem Request** ausgelegt
([ADR 0001](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0001-fastapi-on-cloud-run.md)).

### Prozessmodell

In Produktion startet die Applikation über Gunicorn mit UvicornWorker (`Procfile`):

```
web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

Gunicorn dient als Process-Manager, Uvicorn als ASGI-Worker. Den Port injiziert Cloud Run über
`$PORT`. Lokal wird Uvicorn direkt mit `--reload` betrieben.

### Deployment

Das Deployment erfolgt **manuell** über `deploy.sh`. `gcloud run deploy --source .` baut das Image mit
**Google Cloud Buildpacks** — es gibt bewusst **kein Dockerfile**; der Buildpack erkennt Python an
`requirements.txt`. Anschliessend wird das Image gepusht, eine neue Revision erstellt, der Traffic
umgeleitet und die Secrets werden injiziert.

Ablauf und Rollback: [Runbook 01](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md).

### Technologie-Stack

| Komponente | Technologie |
|------------|-------------|
| Framework | FastAPI >= 0.110.0 |
| ASGI-Server (lokal) | Uvicorn >= 0.27.0 |
| Prozess-Manager (Produktion) | Gunicorn >= 22.0.0 mit UvicornWorker |
| Validierung | Pydantic |
| File-Upload | python-multipart |
| Embeddings | OpenAI API (`text-embedding-3-large`) |
| Vektordatenbank | Pinecone (Environment `gcp-europe-west4`) |
| Datenverarbeitung | Pandas >= 2.0.0 |
| Konfiguration | python-dotenv |
| Laufzeit | Python 3.10+ |
| API Gateway | Apigee X |
| Hosting | Google Cloud Run |
| Secret Management | Google Cloud Secret Manager |

---

## 8. Konfiguration

Die Applikation wird ausschliesslich über Umgebungsvariablen konfiguriert (Klasse `Config` in
`app/config.py`):

| Variable | Standardwert | Beschreibung |
|----------|--------------|--------------|
| `APP_NAME` | `lumina-command-api` | Name des Service |
| `APP_ENV` | `local` | Umgebung (`local` / `production`) |
| `APP_VERSION` | `0.1.0` | Aktuelle Version |
| `LOG_LEVEL` | `info` | Log-Level (`debug`, `info`, `warning`, `error`) |
| `OPENAI_API_KEY` | (leer) | API-Key für die OpenAI-Embedding-Generierung |
| `PINECONE_API_KEY` | (leer) | API-Key für die Pinecone-Vektordatenbank |
| `INTERNAL_API_KEY` | (leer) | Interner API-Key für `/commands/*` (wird von Apigee injiziert) |

`APP_NAME`, `APP_ENV`, `APP_VERSION` und `LOG_LEVEL` werden von `deploy.sh` derzeit **nicht** gesetzt —
in Cloud Run gelten also die Standardwerte, inklusive `APP_ENV=local`.

## 9. Lokale Entwicklung

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
cp .env.example .env            # anschliessend die Keys eintragen

uvicorn app.main:app --reload --port 8080
# Swagger UI: http://127.0.0.1:8080/docs
```

Ausführliche Anleitung inklusive Voraussetzungen: [README.md](https://github.com/eth-library/lumina-command-api/blob/main/README.md).

---

## 10. Bekannte Einschränkungen und offene Punkte

| Thema | Sachverhalt |
|-------|-------------|
| **Plain-CSV-Upload schlägt fehl** | `run_pinecone_upsert` ruft `gzip.decompress` bedingungslos auf. Ein unkomprimiertes `.csv` wird dokumentiert unterstützt, führt aber zu einem Fehler. Offen ist, ob der Code oder die Dokumentation korrigiert wird. |
| **Upsert-Filter fest verdrahtet** | `category_label == "topical"` und `root_term ∈ {domain, facet}` stehen im Code, während Index, Namespace und Embedding-Felder Request-Parameter sind. Ob diese Asymmetrie beabsichtigt ist, ist ungeklärt. |
| **Job-Store nur im Prozessspeicher** | `_jobs` ist ein Dictionary in der Instanz. Bei einer neuen Revision oder einem Instanz-Neustart gehen laufende Jobs verloren, und bei mehreren Instanzen kann eine Status-Abfrage eine Instanz treffen, die den Job nicht kennt. Die Polling-Endpoints sind damit faktisch auf Einzelinstanz-Betrieb ausgelegt. |
| **Vollständige In-Memory-Verarbeitung** | Der gesamte Datensatz liegt als `list[dict]` im Speicher — daher 8 GiB und 3600 s Timeout. Der Datensatz kann nur so gross werden, wie eine Instanz ihn hält. |
| **Datenlage Pinecone** | Der Service läuft in `europe-west6` (Zürich), der Pinecone-Environment ist `gcp-europe-west4` (Niederlande). Vektoren und Metadaten verlassen die Schweiz. |
| **Keine automatisierten Tests** | Das Repository enthält keine Testsuite. Verifikation erfolgt manuell über die Runbooks und `test_data/`. |
| **Keine Specs** | Für die drei bestehenden Module existiert keine Spezifikation — bewusst als Lücke dokumentiert in [specs/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/README.md). |
| **`openapi.json` nicht im Repo** | [README.md](https://github.com/eth-library/lumina-command-api/blob/main/README.md) listet eine Datei `openapi.json`, die es nicht gibt. Das OpenAPI-Dokument wird von FastAPI zur Laufzeit unter `/openapi.json` erzeugt; das ist auch der Vertrag, gegen den Apigee konfiguriert ist. |
| **Runbooks nicht verifiziert** | Runbooks `01`–`04` wurden aus Code und Skripten rekonstruiert und tragen deshalb kein Verifikationsdatum. |

---

## 11. Massgebliche Dokumentation

| Frage | Ort |
|-------|-----|
| **Warum** sieht das System so aus? | [docs/adr/](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr) — Index: [adr/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/README.md) |
| **Was** wird gebaut? | [docs/specs/](https://github.com/eth-library/lumina-command-api/tree/main/docs/specs) — Index: [specs/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/README.md) |
| **Wie** betreiben, deployen, wiederherstellen? | [docs/runbooks/](https://github.com/eth-library/lumina-command-api/tree/main/docs/runbooks) — Index: [runbooks/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/README.md) |
| Onboarding für Entwickler | [README.md](https://github.com/eth-library/lumina-command-api/blob/main/README.md) |
| Arbeitsweise und Dokumentationsregeln | [CLAUDE.md](https://github.com/eth-library/lumina-command-api/blob/main/CLAUDE.md), Abschnitt 5 |

### Architekturentscheide im Überblick

| # | Titel | Status |
|---|-------|--------|
| [0001](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0001-fastapi-on-cloud-run.md) | FastAPI auf Cloud Run, Deployment from Source mit Buildpacks | Accepted |
| [0002](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0002-numbered-step-modules-pipeline.md) | Nummerierte Step-Module als Pipeline-Konvention | Accepted |
| [0003](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0003-openai-embeddings-pinecone-index.md) | OpenAI-Embeddings mit Pinecone-Vektorindex | Accepted |
| [0004](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0004-apigee-as-sole-public-ingress.md) | Apigee X als einziger öffentlicher Zugang | Accepted |
| [0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md) | Shared-Secret als interner API-Key für `/commands/*` | Accepted |
| [0006](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0006-secrets-in-secret-manager.md) | Secrets im Secret Manager, injiziert als Umgebungsvariablen | Accepted |

> ADRs `0001`–`0006` wurden am 2026-07-31 rückwirkend erstellt. Ihre **Decision**-Abschnitte
> beschreiben nachprüfbar den Ist-Zustand; **Context** und **Alternatives considered** sind
> rekonstruiert und können vom damaligen Abwägen abweichen.
