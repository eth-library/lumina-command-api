# Lumina Command API — System Overview

> **Charakter dieses Dokuments:** abgeleitete Zusammenfassung für die interne Confluence-Dokumentation.
> Es hat **keine eigene Autorität** — massgeblich sind die [ADRs](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr), die [Specs](https://github.com/eth-library/lumina-command-api/tree/main/docs/specs), die
> [Runbooks](https://github.com/eth-library/lumina-command-api/tree/main/docs/runbooks) und der Code. Bei Widerspruch gewinnt die Quelle; dieses Dokument wird
> korrigiert. Es wird **auf Anforderung** erstellt und aktualisiert, nicht als Schritt im
> Entwicklungsablauf.
>
> **Stand:** 2026-09-09

---

## Key Facts

| | |
|---|---|
| **Funktionsbereich** | Lumina Control |
| **Tech-Stack** | FastAPI (Python 3.10+) |
| **Google-Projekt** | `ethbib-lumina` (ETHBIB-LUMINA), Projektnummer `171616207524` |
| **Cloud Run Service** | `lumina-command-api`, Region `europe-west6` (Zürich), maximal 3 Instanzen |
| **Fixe Outbound-IP** | `34.65.28.93` — Cloud NAT `lumina-command-api-nat`; für Allow-Listing bei Zielsystemen |
| **Runtime Service Account** | `171616207524-compute@developer.gserviceaccount.com` |
| **API intern (Cloud Run)** | `https://lumina-command-api-171616207524.europe-west6.run.app/` |
| **API extern (Apigee)** | `https://api.library.ethz.ch/lumina/v1/` — sechs Proxies, siehe Abschnitt 4 |
| **Gegenstellen** | OpenAI, Pinecone (schreibend) · Prefect-Server der Lumina Engine (nur lesend) |
| **Swagger UI** | `/docs` am jeweiligen Host |
| **Repository** | https://github.com/eth-library/lumina-command-api |

---

## 1. Zweck und Hauptaufgaben

Die Lumina Command API trennt **Benutzerinteraktion** und **technische Ausführung**. Sie stellt eine
kontrollierte interne Schnittstelle bereit, über die Lumina Studio Aktionen auslösen und den Zustand
der Lumina Engine einsehen kann, ohne direkt auf technische Backend-Prozesse zugreifen zu müssen.

Zwei Arten von Endpoints, in zwei Namensräumen:

- **`/commands/*` — Kommandos.** Schreibende, langlaufende Aufträge: Transformation des
  ETH-UDK-Datensatzes, Embedding-Generierung, Upsert in die Vektordatenbank.
- **`/pipeline/*` — Status.** Lesende Abfragen über die Lumina Engine: welche Datenquellen es gibt,
  wie viele Datensätze sie zuletzt beigetragen haben, welche Pipeline-Läufe laufen, anstehen oder
  gescheitert sind. Diese Endpoints können **nichts** auslösen; sie sind eine read-only Fassade vor
  dem Prefect-Server der Engine ([ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md)).

Innerhalb der **Lumina-Initiative** der ETH-Bibliothek ermöglicht der Service damit:

- Data Readiness für AI-basiertes Discovery
- Metadaten-Anreicherung und -Normalisierung
- Transformationspipelines für nachgelagerte Systeme
- Embedding-Generierung und Vektor-Datenbank-Upserts
- Verarbeitung grosser Datenmengen via Streaming und asynchrone Background-Tasks
- Sichtbarkeit des Pipeline-Zustands für das Studio-Dashboard, ohne dass Studio die Engine kennt

## 2. Interaktionen mit anderen Komponenten

| Gegenstelle | Richtung | Interaktion |
|-------------|----------|-------------|
| Lumina Studio | eingehend | Löst Kommandos aus; liest Datenquellen und Pipeline-Läufe für das Dashboard. Spricht ausschliesslich über Apigee mit dieser API |
| Apigee X | eingehend | Einziger publizierter Zugang; verifiziert Consumer-Keys, tauscht sie gegen den internen Key, cacht die `/pipeline`-Antworten 60 s |
| **Lumina Engine — Prefect-Server** | ausgehend, **nur lesend** | `lumina-box01.ethz.ch:4200`, Prefect 3, ETH-intern, unauthentifiziert. Die API liest Deployments, Flow Runs und Logs; sie schreibt, startet und stoppt nichts |
| OpenAI | ausgehend | Embedding-Generierung |
| Pinecone | ausgehend | Vektor-Upsert |
| **Cloud SQL — Schema `lumina_pipeline`** | ausgehend, nur lesend — **geplant** | Stage-Reports und DAG der Engine, siehe [ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md) (Proposed) |

Die Gegenstellen liegen in eigenen Codebasen; in diesem Repository ist nur die Seite der Command
API sichtbar. Die Lumina Engine — Harvesting, Parsing, Zusammenführung und Deduplizierung der sechs
Quellsysteme — ist ein eigenes Repository ([eth-library/lumina-engine](https://github.com/eth-library/lumina-engine)).

---

## 3. Architektur

### 3.1 Request-Pfad

Externe Konsumenten erreichen die API **ausschliesslich über Apigee X**. Die Cloud-Run-URL ist ein
Implementierungsdetail und wird Konsumenten nicht publiziert ([ADR 0004](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0004-apigee-as-sole-public-ingress.md)).

```
Client (Studio / Postman / Swagger UI)
        │
        │  x-api-key: <Apigee Consumer Key>
        ▼
┌─────────────────────────────────────────────────┐
│  Apigee X — api.library.ethz.ch/lumina/v1/…      │
│  ein Proxy pro Endpoint (sechs)                   │
│  • Consumer-API-Key-Verifikation                  │
│  • CORS (Preflight in Apigee, ohne Backend)       │
│  • Injektion des internen API-Keys                │
│  • /pipeline/*: Response-Cache 60 s               │
└──────────────┬──────────────────────────────────┘
               │  x-api-key: <Internal API Key>
               ▼
┌─────────────────────────────────────────────────┐
│  Lumina Command API — FastAPI auf Cloud Run       │
│  /commands/*        /pipeline/*                   │
└───────┬──────────────────┬──────────────────────┘
        │                  │  Direct VPC Egress → Cloud NAT (34.65.28.93)
        ▼                  ▼
  OpenAI · Pinecone     Prefect-Server der Lumina Engine
  (schreibend)          lumina-box01.ethz.ch:4200  (nur lesend)
```

**Apigee besitzt die Consumer-Identität** (Keys werden dort ausgestellt, skopiert und widerrufen) und
**Apigee besitzt CORS** — die FastAPI-Applikation registriert bewusst **keine** CORS-Middleware. Der
Cloud-Run-Dienst bleibt auf Plattformebene `--allow-unauthenticated` und erzwingt den internen Key im
Applikationscode.

**Der Weg nach Prefect** führt aus Cloud Run über Direct VPC Egress (`lumina-egress-vpc`) und Cloud
NAT mit einer statischen IP ins ETH-Netz. Er ist kein konfigurierter, sondern ein gewachsener Pfad —
eine Firewall-Änderung auf einer der beiden Seiten würde `/pipeline/*` unterbrechen, ohne den Rest
der API zu berühren. Jeder Deploy prüft ihn (Runbook 01, Schritt 4).

### 3.2 Schichtenmodell

```
┌──────────────────────────────────────────────────────────┐
│  FastAPI Application — app/main.py                        │
│  Utility-Endpoints, Router-Registrierung, Logging         │
├──────────────────────────────────────────────────────────┤
│  Authentication Layer — app/auth.py                       │
│  • x-api-key Header-Validierung                           │
│  • Router-Dependency auf /commands/* und /pipeline/*      │
├────────────────────────────┬─────────────────────────────┤
│  Router — commands.py      │  Router — pipeline.py        │
│  • Upload & gzip           │  • drei GET-Endpoints        │
│  • Streaming Response      │  • 502 bei Prefect-Störung   │
│  • Async Jobs (Polling)    │  • 400/404 bei Eingabefehlern│
├────────────────────────────┼─────────────────────────────┤
│  Services (synchron)       │  Service (asynchron)         │
│  transform_eth_udk.py      │  prefect_status.py           │
│  pinecone_upsert.py        │  • httpx, ein Client/Prozess │
│  • Pipeline-Orchestrierung │  • Zuordnung Deployment →    │
│  • Embeddings (OpenAI)     │    Quelle und Stufe          │
│  • Upsert (Pinecone)       │  • Log-Parsing für Mengen    │
├────────────────────────────┴─────────────────────────────┤
│  Transformer Layer — app/transformers/eth_udk/            │
│  Step 1–3 Validierung · 4–6 Normalisierung · 7a–7e        │
│  Transformation · 8 CSV                                   │
└──────────────────────────────────────────────────────────┘
```

Zwei Service-Stile leben nebeneinander: die Pipeline-Services sind synchron und werden per
`asyncio.to_thread` entkoppelt, weil sie CPU-gebunden sind; der Prefect-Service ist `async`, weil er
reines I/O-Fan-out ist — ein Dutzend parallele Leseaufrufe pro Request.

### 3.3 Design-Prinzipien

| Prinzip | Beschreibung |
|---------|--------------|
| Stateless | Kein persistenter Storage — vollständige In-Memory-Verarbeitung |
| Read-only nach Prefect | Der Prefect-Service besitzt keinen Codepfad, der schreiben könnte; nur `GET` und `POST …/filter` bzw. `…/count` sind erlaubt, alles andere wird im Service abgewiesen ([ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md)) |
| Übersetzung an einer Stelle | Prefect kennt Flows und Deployments; die API übersetzt in Quelle, Stufe und letzter Lauf — Studio muss die Engine nicht kennen |
| Zahlen mit Herkunft | Jede Bestandszahl trägt `origin`, `flow`, `measured_at` und im Detail `matched_line` mit der wörtlichen Logzeile. `null` bedeutet «nicht ermittelbar», nie «0» |
| Kein Cache in der API | Jeder Aufruf liest frisch; Caching ist Sache von Apigee |
| Ein Keep-Alive-Client pro Prozess | Vier Verbindungen nach Prefect, wiederverwendet ([ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md)) |
| Modulare Pipeline | Jeder Transformationsschritt ist ein eigenständiges Modul mit einheitlicher Signatur ([ADR 0002](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0002-numbered-step-modules-pipeline.md)) |
| gzip-Unterstützung | Uploads als `.json.gz` / `.csv.gz` (Workaround für das ~32 MB Request-Limit von Cloud Run) |
| Streaming Response | Grosse Ergebnisse werden als `StreamingResponse` zurückgegeben |
| Async Background-Tasks | Langlebige Operationen laufen als Polling-basierte Hintergrundaufgaben |

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

| Pfad | Methode | Beschreibung | Apigee-Proxy |
|------|---------|--------------|--------------|
| `/commands/transform-eth-udk-json` | POST | ETH-UDK-Datensatz transformieren → JSON | `lumina-transform-eth-udk-json` |
| `/commands/transform-eth-udk-csv` | POST | ETH-UDK-Datensatz transformieren → CSV | `lumina-transform-eth-udk-csv` |
| `/commands/upsert-pinecone` | POST | Embedding-Generierung und Upsert nach Pinecone (synchron) | `lumina-upsert-pinecone` |
| `/commands/upsert-pinecone-polling` | POST | Asynchronen Upsert-Job starten, gibt `job_id` zurück | `lumina-upsert-pinecone-polling` |
| `/commands/upsert-pinecone-polling/{job_id}/status` | GET | Status eines Upsert-Jobs abfragen | derselbe |

Ablauf über alle fünf Kommandos: [Runbook 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md).
Confluence-Seiten je Endpoint: [docs/endpoints/](https://github.com/eth-library/lumina-command-api/tree/main/docs/endpoints).

### Pipeline-Endpoints (erfordern `x-api-key`, read-only)

| Pfad | Methode | Beschreibung | Apigee-Proxy |
|------|---------|--------------|--------------|
| `/pipeline/sources` | GET | Die sechs Datenquellen der Engine mit Stufen, letztem Lauf und Bestandszahl | `lumina-pipeline-sources` |
| `/pipeline/sources/{source_id}` | GET | Eine Quelle mit Kennzahlen je Stufe, inkl. der gemeinsamen Unify-Stufe | derselbe |
| `/pipeline/runs` | GET | Flow Runs, neueste zuerst; Filter `state` und `deployment`, `limit` bis 200 | `lumina-pipeline-runs` |

Derselbe `x-api-key` wie bei `/commands/*`. Spezifikation mit Abnahmekriterien:
[Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md).
Contract fürs Entwicklerportal, auf Englisch: [docs/openapi/](https://github.com/eth-library/lumina-command-api/tree/main/docs/openapi).
Confluence-Seiten: [pipeline-sources](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources.md), [pipeline-sources-source-id](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources-source-id.md), [pipeline-runs](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-runs.md).

Apigee legt pro Endpoint einen Proxy an, mit vollem Basepath (`/lumina/v1/pipeline/sources`). Ein
neuer Backend-Pfad braucht darum einen neuen Proxy — [Runbook 05](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/05-apigee-proxy.md).

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

**Pipeline-Endpoints** — nur Query-Parameter, kein Body:

| Parameter | Endpoint | Beschreibung |
|-----------|----------|--------------|
| `limit` | `/runs` | 1–200, Standard 50 |
| `state` | `/runs` | Kommaseparierte Prefect-Zustände; unbekannte werden mit `400` abgewiesen, nicht ignoriert |
| `deployment` | `/runs` | Kommaseparierte Deployment-Namen; unbekannte ebenso `400` |

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

### 5.3 Polling-Variante

`/commands/upsert-pinecone-polling` legt einen Job mit UUID an, startet die Verarbeitung als
`asyncio`-Task und antwortet sofort mit `{"job_id": ..., "status": "accepted"}`. Der Status-Endpoint
liefert den fortlaufend aktualisierten Fortschritt (`status`, `phase`, `progress_percent`, am Ende
`result` oder `error`). Der Job-Store ist ein **In-Memory-Dictionary** — mit den Folgen aus
Abschnitt 10.

### 5.4 Pipeline-Status aus Prefect

Implementiert in `app/services/prefect_status.py` ([Spec 04](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/04-prefect-pipeline-status.md), [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md)).

Die Lumina Engine verarbeitet sechs Quellsysteme in einem wöchentlichen Prefect-Lauf (sonntags um
Mitternacht): Harvest → Parse → Hierarchy → Merge → Unify → Deduplicate → Load. Prefect kennt dabei
nur Flows, Deployments und Flow Runs — keinen Begriff «Datenquelle» und keine Kennzahlen.

Die API übersetzt in drei Schritten:

1. **Zuordnung.** Eine Tabelle im Service bildet die 20 Prefect-Deployments über den
   Entrypoint-Funktionsnamen (`parse_alma_eth`, nicht den umbenennbaren Anzeigenamen) auf sechs
   Quellen und ihre Stufen ab. Fünf Deployments sind quellenübergreifend (`merge`, `unify`,
   `deduplicate`, `load`, `orchestrate`) und tragen `source_id: null`.
2. **Letzter Lauf je Stufe** aus Prefect: Zustand, Start, Ende, Laufzeit, Wiederholungen. Eine Stufe
   ohne Lauf liefert `last_run: null` — ein Normalzustand.
3. **Bestandszahlen aus Logzeilen.** Der Prefect-Server speichert keine Artifacts und keine Task
   Runs; die Zahlen existieren nur als Freitext (`Total records: 4415363`). Drei Regex-Muster, jedes an
   genau einen Flow gebunden, lesen sie aus. Findet sich keine Zeile, ist der Wert `null` — nie `0`.

| Quelle (`source_id`) | Quellsystem | Grössenordnung |
|---|---|---|
| `slsp_eth` | SLSP ETH, Alma-Institutionszone | 4,4 Mio. |
| `slsp_network` | SLSP Network, Alma-Netzwerkzone | 18,6 Mio. |
| `epics` | E-Pics Bildarchiv | 1,1 Mio. |
| `erara` | E-Rara, digitalisierte Drucke | 45'000 |
| `research_collection` | Research Collection der ETH | 307'000 |
| `semantic_scholar` | Semantic Scholar S2AG | 237 Mio. |

Zwei Eigenheiten, die jede Darstellung berücksichtigen muss: Die Unify-Zahl der beiden SLSP-Quellen
ist **gemeinsam** — `Merge: ALMA` faltet beide Zonen zu einem Datensatz pro Werk, bevor gezählt wird;
das Feld `covers` nennt darum bei jeder Kennzahl die Quellen, für die sie gilt. Und Parse- und
Unify-Zahl derselben Quelle dürfen abweichen; die API rechnet sie bewusst nicht gegeneinander auf.

**Geplant** ([ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md), Proposed): Die Engine schreibt Ein- und Ausgangsmengen je Lauf in eine
Tabelle auf Cloud SQL; die API liest sie über `flow_run_id` zum Prefect-Lauf dazu. Das Log-Parsing
bleibt als Rückfallebene, `origin` sagt pro Zahl, woher sie kommt.

---

## 6. Sicherheit

### API-Key-Authentifizierung

Alle `/commands/*`- und `/pipeline/*`-Endpoints sind durch eine interne API-Key-Prüfung abgesichert
(`app/auth.py`). Der Key wird über den Header `x-api-key` übergeben und gegen die Umgebungsvariable
`INTERNAL_API_KEY` validiert ([ADR 0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md)).

| Szenario | HTTP-Status | Antwort |
|----------|-------------|---------|
| Header fehlt | 401 | `{"detail": "Missing API key."}` |
| Falscher Key | 401 | `{"detail": "Invalid API key."}` |
| Key nicht konfiguriert | 500 | `{"detail": "INTERNAL_API_KEY not configured."}` |
| Korrekter Key | — | Request wird verarbeitet |

Die Prüfung hängt als FastAPI-Dependency **am Router**, nicht an den einzelnen Endpoints. Jeder
Router deklariert sie selbst — ein neuer Router erbt sie nicht automatisch, und das ist der eine
Punkt, an dem ein neuer Namensraum versehentlich offen bleiben könnte:

```python
router = APIRouter(prefix="/commands", tags=["commands"], dependencies=[Depends(verify_api_key)])
router = APIRouter(prefix="/pipeline", tags=["pipeline"], dependencies=[Depends(verify_api_key)])
```

Die Utility-Endpoints (`/`, `/health`, `/version`) sind bewusst nicht geschützt. Der `500` bei
fehlender Konfiguration ist Absicht: ein fehlkonfiguriertes Deployment soll laut scheitern, statt
jeden Request anzunehmen.

Im Produktionsbetrieb injiziert Apigee den internen Key — in jedem der sechs Proxies als Literal in
der Policy `AM-InjectBackendApiKey`. Externe Konsumenten verwenden ausschliesslich ihren Apigee
Consumer Key und sehen den internen Key nie. Eine Rotation trifft alle sechs Proxies
([Runbook 02](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/02-rotate-secrets.md)).

**Der Prefect-Server ist unauthentifiziert.** Wer ihn im ETH-Netz erreicht, kann lesen — und
schreiben. Die API stellt ihre Schreibunfähigkeit darum nicht durch Konvention, sondern durch
Konstruktion sicher: es gibt keinen Codepfad, der etwas anderes als Lesepfade aufruft.

### Secret Management

Drei Secrets liegen im **Google Cloud Secret Manager** ([ADR 0006](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0006-secrets-in-secret-manager.md)):

| Secret | Beschreibung |
|--------|--------------|
| `OPENAI_API_KEY` | API-Key für die OpenAI-Embedding-Generierung |
| `PINECONE_API_KEY` | API-Key für die Pinecone-Vektordatenbank |
| `INTERNAL_API_KEY` | Interner API-Key zur Absicherung von `/commands/*` und `/pipeline/*` |

`PREFECT_API_URL` ist **kein** Secret — Prefect hat keine Zugangsdaten, die es zu schützen gäbe —
und wird als gewöhnliche Umgebungsvariable gesetzt.

- **Lokal:** Werte kommen aus `.env` (via `python-dotenv`). `.env` steht in `.gitignore` und wird
  **nie** committet; `.env.example` ist die committete Vorlage.
- **Cloud Run:** `deploy.sh` referenziert die Secrets über `--set-secrets=NAME=SECRET_NAME:latest`
  und die Umgebungsvariablen über `--update-env-vars`; beide landen als Umgebungsvariablen im
  Container und werden von `Config` in `app/config.py` gelesen — **derselbe Codepfad wie lokal**.
- `setup-secrets.sh` liest die drei Keys aus der lokalen `.env`, legt fehlende Secrets an und lädt
  den aktuellen Wert als neue Version hoch.
- Der Runtime Service Account benötigt einmalig projektweit `roles/secretmanager.secretAccessor`.

**Prozeduren** — Rotation, Bootstrap, Deployment und Apigee sind in den Runbooks beschrieben und dort
massgeblich; dieses Dokument wiederholt sie bewusst nicht:

- [Runbook 01 — Deploy to Cloud Run](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md)
- [Runbook 02 — Rotate a secret](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/02-rotate-secrets.md)
- [Runbook 03 — Bootstrap a GCP project](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/03-gcp-project-bootstrap.md)
- [Runbook 04 — Run the ETH UDK pipeline end to end](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/04-run-udk-pipeline.md)
- [Runbook 05 — Publish an endpoint through Apigee X](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/05-apigee-proxy.md)

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
| Instanzen | maximal 3 (`--max-instances=3`) |
| Egress | Direct VPC Egress über `lumina-egress-vpc`, Cloud Router `lumina-egress-router`, Cloud NAT `lumina-command-api-nat` |
| Fixe Outbound-IP | `34.65.28.93` (`lumina-command-api-egress-ip`) |
| NAT-Port-Zuteilung | dynamisch, 64–4096 Ports pro Instanz — seit 2026-09-09, siehe Abschnitt 10 |

Die Dimensionierung von Memory und Timeout ist auf den Lauf über den **vollständigen
UDK-Datensatz in einem Request** ausgelegt ([ADR 0001](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0001-fastapi-on-cloud-run.md)). Das
Instanz-Maximum begrenzt die Verbindungen, die der Service nach Prefect öffnen kann: ein Worker pro
Instanz, vier Keep-Alive-Verbindungen pro Worker ([ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md)).

### Prozessmodell

In Produktion startet die Applikation über Gunicorn mit UvicornWorker (`Procfile`), ein Worker pro
Instanz. Den Port injiziert Cloud Run über `$PORT`. Lokal wird Uvicorn direkt mit `--reload` betrieben.

### Deployment

Das Deployment erfolgt **manuell** über `deploy.sh`. `gcloud run deploy --source .` baut das Image mit
**Google Cloud Buildpacks** — es gibt bewusst **kein Dockerfile**. Hochgeladen wird das
**Arbeitsverzeichnis**, nicht der Git-Stand; nicht committete Änderungen deployen stillschweigend
mit. Die Artifact-Registry-Frage beim Deploy ist das Erkennungszeichen für ein falsch gesetztes
`gcloud`-Projekt.

Ablauf, Prüfung und Rollback: [Runbook 01](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md).

### Technologie-Stack

| Komponente | Technologie |
|------------|-------------|
| Framework | FastAPI >= 0.110.0 |
| ASGI-Server (lokal) | Uvicorn >= 0.27.0 |
| Prozess-Manager (Produktion) | Gunicorn >= 22.0.0 mit UvicornWorker |
| Validierung | Pydantic |
| File-Upload | python-multipart |
| HTTP-Client | httpx >= 0.27.0 — nur für Prefect |
| Embeddings | OpenAI API (`text-embedding-3-large`) |
| Vektordatenbank | Pinecone (Environment `gcp-europe-west4`) |
| Datenverarbeitung | Pandas >= 2.0.0 |
| Konfiguration | python-dotenv |
| Laufzeit | Python 3.10+ |
| API Gateway | Apigee X |
| Hosting | Google Cloud Run |
| Secret Management | Google Cloud Secret Manager |
| Orchestrierung der Engine (Gegenstelle) | Prefect 3, Docker Compose auf `lumina-box01` |

---

## 8. Konfiguration

Die Applikation wird ausschliesslich über Umgebungsvariablen konfiguriert (Klasse `Config` in
`app/config.py`):

| Variable | Standardwert | In Cloud Run gesetzt | Beschreibung |
|----------|--------------|----------------------|--------------|
| `APP_NAME` | `lumina-command-api` | nein | Name des Service |
| `APP_ENV` | `local` | `production` | Umgebung |
| `APP_VERSION` | `0.1.0` | nein | Version — in Cloud Run gilt der Standardwert |
| `LOG_LEVEL` | `info` | nein | Log-Level |
| `OPENAI_API_KEY` | (leer) | Secret | OpenAI-Embedding-Generierung |
| `PINECONE_API_KEY` | (leer) | Secret | Pinecone-Vektordatenbank |
| `INTERNAL_API_KEY` | (leer) | Secret | Interner API-Key (wird von Apigee injiziert) |
| `PREFECT_API_URL` | `http://lumina-box01.ethz.ch:4200/api` | ja | Prefect-Server der Lumina Engine |

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

Die `/pipeline`-Endpoints funktionieren lokal nur aus dem ETH-Netz oder per VPN, weil
`lumina-box01` intern ist. Ausführliche Anleitung: [README.md](https://github.com/eth-library/lumina-command-api/blob/main/README.md).

---

## 10. Bekannte Einschränkungen und offene Punkte

| Thema | Sachverhalt |
|-------|-------------|
| **Bestandszahlen aus Logzeilen** | Die `/pipeline`-Zahlen stammen aus Regex auf Prefect-Logs. Wird in der Engine eine Logmeldung umformuliert, wird aus der Zahl still `null` — kein Fehler, kein Hinweis. Bewusst so gewählt: lieber keine Zahl als eine falsche. Die dauerhafte Lösung ist [ADR 0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md). |
| **Prefect ist eine Verfügbarkeitsabhängigkeit** | Ist der Prefect-Server oder der Netzwerkweg dorthin gestört, liefert `/pipeline/*` `502`; `/commands/*` arbeitet weiter. Der Weg von Cloud Run ins ETH-Netz ist gewachsen, nicht konfiguriert. |
| **Prefect-Historie erst ab 2026-09-01** | Die Prefect-Metadatenbank wurde an diesem Tag neu angelegt; frühere Läufe sind dort nicht vorhanden. Prefect 3 löscht keine Flow Runs — die Datenbank war schlicht leer. |
| **Verbindungsburst nach Prefect — behoben** | Am 2026-09-09 lehnte der Weg nach Prefect Verbindungen ab, weil ein Client pro Request bis zu 15 TCP-Verbindungen in 50 ms öffnete und Cloud NAT mit 64 statischen Ports pro Instanz nach vier Seitenaufrufen erschöpft war. Behoben auf beiden Seiten: ein geteilter Keep-Alive-Client ([ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md)) und dynamische NAT-Port-Zuteilung (Runbook 03, Schritt 8). Nachgewiesen mit 60 ungecachten Aufrufen in Folge. |
| **Plain-CSV-Upload schlägt fehl** | `run_pinecone_upsert` ruft `gzip.decompress` bedingungslos auf. Ein unkomprimiertes `.csv` wird dokumentiert unterstützt, führt aber zu einem Fehler. Offen ist, ob der Code oder die Dokumentation korrigiert wird. |
| **Upsert-Filter fest verdrahtet** | `category_label == "topical"` und `root_term ∈ {domain, facet}` stehen im Code, während Index, Namespace und Embedding-Felder Request-Parameter sind. Ob diese Asymmetrie beabsichtigt ist, ist ungeklärt. |
| **Job-Store nur im Prozessspeicher** | `_jobs` ist ein Dictionary in der Instanz. Bei einer neuen Revision gehen laufende Jobs verloren, und bei mehreren Instanzen kann eine Status-Abfrage eine Instanz treffen, die den Job nicht kennt. Mit maximal 3 Instanzen ist das seltener, nicht gelöst. |
| **Vollständige In-Memory-Verarbeitung** | Der gesamte UDK-Datensatz liegt als `list[dict]` im Speicher — daher 8 GiB und 3600 s Timeout. |
| **Datenlage Pinecone** | Der Service läuft in `europe-west6` (Zürich), der Pinecone-Environment ist `gcp-europe-west4` (Niederlande). Vektoren und Metadaten verlassen die Schweiz. |
| **Keine automatisierten Tests** | Das Repository enthält keine Testsuite. Verifikation erfolgt manuell über die Runbooks und `test_data/`; die `/pipeline`-Endpoints wurden gegen den echten Prefect-Server abgenommen, das Vorgehen steht in Spec 04. |
| **Specs nur für Modul 04** | Die drei älteren Module (UDK-Pipeline, Pinecone-Upsert, Auth) haben keine Spezifikation — bewusst als Lücke dokumentiert in [specs/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/README.md). Spec 04 ist die erste, die vor dem Code geschrieben wurde. |
| **OpenAPI nur für `/pipeline`** | [docs/openapi/](https://github.com/eth-library/lumina-command-api/tree/main/docs/openapi) versioniert den Gateway-Contract für die Pipeline-Endpoints. Für `/commands/*` gibt es weiterhin kein Dokument im Repository; dort gilt das zur Laufzeit erzeugte `/openapi.json`. |
| **Interner Key in sechs Proxies** | Der `INTERNAL_API_KEY` liegt in jedem Apigee-Proxy als Literal. Eine Rotation muss alle sechs treffen; eine verschlüsselte KVM wäre eine Stelle — eine offene Entscheidung. |
| **Runbooks teilweise unverifiziert** | `01`–`04` wurden aus Code und Skripten rekonstruiert und tragen kein Verifikationsdatum. `01` und `03` wurden im September 2026 in Teilen tatsächlich durchlaufen und dabei korrigiert; `05` trägt ein bewusst unvollständiges Datum. |

---

## 11. Massgebliche Dokumentation

| Frage | Ort |
|-------|-----|
| **Warum** sieht das System so aus? | [docs/adr/](https://github.com/eth-library/lumina-command-api/tree/main/docs/adr) — Index: [adr/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/README.md) |
| **Was** wird gebaut? | [docs/specs/](https://github.com/eth-library/lumina-command-api/tree/main/docs/specs) — Index: [specs/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/specs/README.md) |
| **Wie** betreiben, deployen, wiederherstellen? | [docs/runbooks/](https://github.com/eth-library/lumina-command-api/tree/main/docs/runbooks) — Index: [runbooks/README.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/README.md) |
| Contract fürs Entwicklerportal | [docs/openapi/](https://github.com/eth-library/lumina-command-api/tree/main/docs/openapi) |
| Confluence-Seiten je Endpoint | [docs/endpoints/](https://github.com/eth-library/lumina-command-api/tree/main/docs/endpoints) |
| Onboarding für Entwickler | [README.md](https://github.com/eth-library/lumina-command-api/blob/main/README.md) |
| Arbeitsweise und Dokumentationsregeln | [CLAUDE.md](https://github.com/eth-library/lumina-command-api/blob/main/CLAUDE.md), Abschnitt 5 |

### Architekturentscheide im Überblick

| # | Titel | Status |
|---|-------|--------|
| [0001](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0001-fastapi-on-cloud-run.md) | FastAPI auf Cloud Run, Deployment from Source mit Buildpacks | Accepted |
| [0002](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0002-numbered-step-modules-pipeline.md) | Nummerierte Step-Module als Pipeline-Konvention | Accepted |
| [0003](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0003-openai-embeddings-pinecone-index.md) | OpenAI-Embeddings mit Pinecone-Vektorindex | Accepted |
| [0004](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0004-apigee-as-sole-public-ingress.md) | Apigee X als einziger öffentlicher Zugang | Accepted |
| [0005](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0005-shared-secret-internal-api-key.md) | Shared-Secret als interner API-Key | Accepted |
| [0006](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0006-secrets-in-secret-manager.md) | Secrets im Secret Manager, injiziert als Umgebungsvariablen | Accepted |
| [0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) | Read-only Fassade über den Prefect-Server der Lumina Engine | Accepted, ergänzt durch 0009 |
| [0008](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0008-stage-reports-from-cloud-sql.md) | Stage-Reports und DAG aus Cloud SQL, verknüpft über die Prefect-Run-ID | Proposed |
| [0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md) | Ein geteilter Keep-Alive-Client für Prefect-Zugriffe | Accepted |

> ADRs `0001`–`0006` wurden am 2026-07-31 rückwirkend erstellt; ihre **Decision**-Abschnitte
> beschreiben nachprüfbar den Ist-Zustand, **Context** und **Alternatives considered** sind
> rekonstruiert. `0007` ist der erste ADR, der vor seiner Umsetzung geschrieben wurde; `0008` wartet
> auf die Umsetzung in der Lumina Engine.
