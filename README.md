# Lumina Command API

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![Cloud Run](https://img.shields.io/badge/Google%20Cloud-Run-blue)
![License](https://img.shields.io/badge/License-Apache%202.0-orange)

---

## Overview

**Lumina Command API** is a central backend service in the [Lumina ecosystem](https://github.com/eth-library) of the ETH Library. It provides a unified API layer for executing data transformation pipelines, enrichment workflows, and other processing tasks on structured library data.

Within the broader **Lumina initiative**, this service enables:

- Data readiness for AI-based discovery
- Metadata enrichment and normalization
- Transformation pipelines for downstream systems
- Embedding generation and vector database upserts
- Scalable processing of large datasets via streaming and async background tasks

## Architecture

```
Client (Browser / Postman / Application)
        │
        │  x-api-key (consumer key)
        ▼
┌──────────────────────────┐
│       Apigee X           │
│  api.library.ethz.ch     │
│  • API key verification  │
│  • CORS handling         │
│  • Backend key injection │
└──────────┬───────────────┘
           │  x-api-key (internal key)
           ▼
┌──────────────────────────┐
│   Lumina Command API     │
│   (FastAPI on Cloud Run) │
│  • Internal key auth     │
│  • Pipeline execution    │
│  • Embedding generation  │
└──────────┬───────────────┘
           │
           ▼
   Output (JSON / CSV)
   Pinecone (vectors)
```

External consumers access the API exclusively through **Apigee X**. The Cloud Run backend is protected by an internal API key that Apigee injects transparently.

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI >= 0.110.0 |
| ASGI Server (local) | Uvicorn >= 0.27.0 |
| WSGI Server (production) | Gunicorn >= 22.0.0 with UvicornWorker |
| Validation | Pydantic |
| Embeddings | OpenAI API (text-embedding-3-large) |
| Vector Database | Pinecone |
| Data Processing | Pandas >= 2.0.0 |
| API Gateway | Apigee X |
| Hosting | Google Cloud Run |
| Secret Management | Google Cloud Secret Manager |

---

## API Endpoints

### Utility Endpoints (no authentication)

| Path | Method | Description |
|------|--------|-------------|
| `/` | GET | Service name and environment |
| `/health` | GET | Health check |
| `/version` | GET | Name, version, and environment |

### Command Endpoints (require `x-api-key` header)

| Path | Method | Description |
|------|--------|-------------|
| `/commands/transform-eth-udk-json` | POST | Transform ETH UDK dataset → JSON |
| `/commands/transform-eth-udk-csv` | POST | Transform ETH UDK dataset → CSV |
| `/commands/upsert-pinecone` | POST | Embed and upsert records to Pinecone |
| `/commands/upsert-pinecone-polling` | POST | Start async upsert job (returns job ID) |
| `/commands/upsert-pinecone-polling/{job_id}/status` | GET | Poll upsert job status |

### Input Format (Transform Endpoints)

| Key | Type | Description |
|-----|------|-------------|
| `source_file` | File | ETH UDK dataset (`.json` or `.json.gz`) |
| `rootterms_file` | File | Root terms lookup (`.json` or `.json.gz`) |

### Input Format (Upsert Endpoints)

| Key | Type | Description |
|-----|------|-------------|
| `file` | File | CSV file (`.csv` or `.csv.gz`) |
| `index_name` | string | Pinecone index name |
| `namespace` | string | Pinecone namespace |
| `embedding_fields` | string | JSON array of field names to embed, e.g. `'["descriptor_eng"]'` |

### Large File Handling

Due to Cloud Run request limits (~32 MB), gzip compression is supported and recommended:

- `.json` / `.csv` → supported
- `.json.gz` / `.csv.gz` → recommended for large files

---

## Developer Guide

### Prerequisites

- Python 3.10+
- Git
- Google Cloud SDK (`gcloud`)
- VS Code (recommended)

### 1. Clone Repository

```bash
git clone https://github.com/eth-library/lumina-command-api.git
cd lumina-command-api
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
```

Activate:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the template and fill in your keys:

```bash
cp .env.example .env
```

Then edit `.env` with your actual values:

```env
PYTHONPATH=.
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=pcsk_...
INTERNAL_API_KEY=your-secret-key-here
```

The `.env` file is listed in `.gitignore` and must never be committed.

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key for OpenAI embedding generation |
| `PINECONE_API_KEY` | API key for Pinecone vector database |
| `INTERNAL_API_KEY` | Internal API key for `/commands/*` endpoint authentication |

### 5. Configure VS Code (optional)

- Open the project folder
- `Ctrl + Shift + P` → *Python: Select Interpreter*
- Select the `.venv` interpreter

### 6. Run Local Server

```bash
uvicorn app.main:app --reload --port 8080
```

- **Swagger UI:** http://127.0.0.1:8080/docs
- **Health check:** http://127.0.0.1:8080/health

## Google Cloud Setup

### 1. Authenticate and Set Project

```bash
gcloud auth login
gcloud projects create your-project-id
gcloud config set project your-project-id
```

### 2. Enable Required APIs

```bash
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

### 3. Set Region

```bash
gcloud config set run/region europe-west6
```

### 4. Grant Secret Manager Access

The Cloud Run service account needs permission to read secrets:

```bash
gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

This is a one-time setup.

### 5. Upload Secrets

The `setup-secrets.sh` script reads keys from your local `.env` and creates or updates them in Google Cloud Secret Manager:

```bash
./setup-secrets.sh
```

The script handles `OPENAI_API_KEY`, `PINECONE_API_KEY`, and `INTERNAL_API_KEY`.

---

## Deployment

### Deploy to Cloud Run

```bash
./deploy.sh
```

This script:

1. Builds a container image from source via Google Cloud Buildpacks
2. Pushes the image to Google Container Registry
3. Creates a new Cloud Run revision and routes traffic to it
4. Injects secrets from Secret Manager as environment variables

### View Logs

```bash
gcloud run services logs read lumina-command-api --region europe-west6
```

### Key Rotation Workflow

1. Update the key in your `.env` file
2. Run `./setup-secrets.sh` (creates a new secret version)
3. Run `./deploy.sh` (deploys a new revision with the updated secret)

---

## Project Structure

```
lumina-command-api/
├── app/
│   ├── main.py                  # FastAPI application entry point
│   ├── config.py                # Environment variable configuration
│   ├── auth.py                  # API key authentication dependency
│   ├── routers/
│   │   └── commands.py          # All /commands/* endpoint definitions
│   ├── services/
│   │   ├── transform_eth_udk.py # ETH UDK transformation pipeline orchestrator
│   │   └── pinecone_upsert.py   # Embedding generation and Pinecone upsert
│   └── transformers/
│       └── eth_udk/
│           ├── step1_check_unique_descriptors.py
│           ├── step2_check_non_dictionary_variants.py
│           ├── step3_validate_json_structure.py
│           ├── step4_merge_variants_by_language.py
│           ├── step5_add_broader_terms_names.py
│           ├── step6_add_related_terms_names.py
│           ├── step7a_simplify_json.py
│           ├── step7b_add_level.py
│           ├── step7c_clean_transaction_date.py
│           ├── step7d_add_cat_root_term.py
│           ├── step7e_propagate_root_terms.py
│           └── step8_json_to_csv.py
├── docs/
│   ├── adr/                     # Architecture Decision Records — why the system looks like it does
│   ├── specs/                   # Module specs — what gets built, before it is built
│   └── runbooks/                # Operational procedures — deploy, rotate secrets, run pipelines
├── test_data/                   # Sample datasets for testing
├── deploy.sh                    # Cloud Run deployment script
├── setup-secrets.sh             # Secret Manager setup script
├── Procfile                     # Production process definition (Gunicorn)
├── requirements.txt             # Python dependencies
├── openapi.json                 # OpenAPI 3.0.3 spec (for Apigee)
└── LICENSE                      # Apache 2.0
```

## License

This project is licensed under the [Apache License 2.0](LICENSE).

