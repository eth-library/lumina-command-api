# Lumina Command API

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![Cloud Run](https://img.shields.io/badge/Google%20Cloud-Run-blue)
![License](https://img.shields.io/badge/License-Apache%202.0-orange)

---

## Overview

**Lumina Command API** is a central backend service for the Lumina ecosystem. It provides a unified API layer for executing data transformation pipelines, enrichment workflows, and other processing tasks on structured library data.

Within the broader **Lumina initiative**, this service enables:

- Data readiness for AI-based discovery
- Metadata enrichment and normalization
- Transformation pipelines for downstream systems
- Scalable processing of large datasets

---

## Architecture (Simplified)

```
Client (Postman / Lumina Studio)
            │
            ▼
    Lumina Command API (FastAPI)
            │
            ▼
 Transformation Pipelines
            │
            ▼
    Output (JSON / CSV)
```

---

## User Guide

### Available Endpoints

#### 1. Transform ETH UDK → JSON

**POST** `/commands/transform-eth-udk-json`

Returns transformed and enriched JSON.

---

#### 2. Transform ETH UDK → CSV

**POST** `/commands/transform-eth-udk-csv`

Returns transformed and enriched CSV.

---

### Input Format

Both endpoints expect:

| Key | Type | Description |
|-----|------|------------|
| source_file | File | ETH UDK dataset (.json or .json.gz) |
| rootterms_file | File | Root terms lookup (.json or .json.gz) |

---

### Output

- JSON → streamed response
- CSV → streamed response

---

### Large File Handling

Due to Cloud Run request limits (~32MB), gzip is supported:

- `.json` → supported
- `.json.gz` → recommended

---

## Developer Guide

### Local Development Setup (Windows + VS Code)

#### Prerequisites

- Python 3.10+
- VS Code
- Git
- Google Cloud SDK (`gcloud`)

---

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd lumina-command-api
```

---

### 2. Create Virtual Environment

```bash
python -m venv .venv
```

Activate:

```bash
.venv\Scripts\activate
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure VS Code

- Open project folder
- `Ctrl + Shift + P` → *Python: Select Interpreter*
- Select `.venv`

---

### 5. Run Local Server

```bash
uvicorn app.main:app --reload --port 8080
```

Swagger UI:

```
http://127.0.0.1:8080/docs
```

---

## Google Cloud Setup

### Login

```bash
gcloud auth login
```

---

### Create Project

```bash
gcloud projects create lumina-project
```

```bash
gcloud config set project lumina-project
```

---

### Enable APIs

```bash
gcloud services enable run.googleapis.com
```

---

### Set Region

```bash
gcloud config set run/region europe-west6
```

---

## Deployment

### Using deploy.sh

```bash
./deploy.sh
```

---

## Commands Summary

### Start Local Server

```bash
uvicorn app.main:app --reload --port 8080
```

---

### Run Pipeline Test

```bash
python test_pipeline.py
```

---

### Deploy to Cloud Run

```bash
./deploy.sh
```

---

### View Logs

```bash
gcloud run services logs read lumina-command-api --region europe-west6
```

---

## Project Structure

```
app/
  main.py
  config.py
  routers/
    commands.py
  services/
    transform_eth_udk.py
  transformers/
    eth_udk/
      step1_...
      step2_...
      ...
```

---

## Planned Extensions

- Additional transformation pipelines
- AI-based enrichment workflows
- Classification services
- Async processing for large jobs

---

## License

This project is licensed under the Apache License 2.0.

