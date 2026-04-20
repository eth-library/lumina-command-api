from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, JSONResponse
import json
import io
import gzip
import logging
import asyncio
import uuid

from app.services.transform_eth_udk import run_transform_eth_udk
from app.services.pinecone_upsert import run_pinecone_upsert
from app.transformers.eth_udk.step8_json_to_csv import transform as step8

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commands", tags=["commands"])

# In-memory job store for polling-based upsert
_jobs: dict[str, dict] = {}

async def read_json_file(upload_file: UploadFile, content_encoding: str | None = None):
    """
    Reads an uploaded JSON file.
    Supports:
    - plain .json files
    - .json.gz files
    - files sent with Content-Encoding: gzip
    """
    content = await upload_file.read()

    is_gzip_file = upload_file.filename and upload_file.filename.endswith(".gz")
    is_gzip_header = content_encoding == "gzip"

    if is_gzip_file or is_gzip_header:
        content = gzip.decompress(content)

    return json.loads(content)

# -------------------------
# 1️⃣ JSON Endpoint
# -------------------------
@router.post("/transform-eth-udk-json")
async def transform_eth_udk_json(
    request: Request,
    source_file: UploadFile = File(...),
    rootterms_file: UploadFile = File(...)
):
    source_data = await read_json_file(
        source_file,
        request.headers.get("content-encoding")
    )
    rootterms_data = await read_json_file(
        rootterms_file,
        request.headers.get("content-encoding")
    )

    data = run_transform_eth_udk(source_data, rootterms_data)

    json_str = json.dumps(data)

    return StreamingResponse(
        io.StringIO(json_str),
        media_type="application/json"
    )


# -------------------------
# 2️⃣ CSV Endpoint
# -------------------------
@router.post("/transform-eth-udk-csv")
async def transform_eth_udk_csv(
    request: Request,
    source_file: UploadFile = File(...),
    rootterms_file: UploadFile = File(...)
):
    source_data = await read_json_file(
        source_file,
        request.headers.get("content-encoding")
    )
    rootterms_data = await read_json_file(
        rootterms_file,
        request.headers.get("content-encoding")
    )

    data = run_transform_eth_udk(source_data, rootterms_data)
    csv_content = step8(data)

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv"
    )


# -------------------------
# 3️⃣ Pinecone Upsert Endpoint
# -------------------------
@router.post("/upsert-pinecone")
async def upsert_pinecone(
    file: UploadFile = File(...),
    index_name: str = Form(...),
    namespace: str = Form(...),
    embedding_fields: str = Form(...),
):
    # Parse embedding_fields JSON string
    try:
        fields_list = json.loads(embedding_fields)
        if not isinstance(fields_list, list) or not all(isinstance(f, str) for f in fields_list):
            raise ValueError("embedding_fields must be a JSON array of strings.")
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"detail": "embedding_fields must be a valid JSON array, e.g. '[\"descriptor_eng\"]'."},
        )

    try:
        file_bytes = await file.read()
        result = await asyncio.to_thread(
            run_pinecone_upsert,
            file_bytes=file_bytes,
            index_name=index_name,
            namespace=namespace,
            embedding_fields=fields_list,
        )
        return result
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:
        logger.exception("Upsert failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# -------------------------
# 4️⃣ Pinecone Upsert Polling Endpoint
# -------------------------
async def _run_upsert_job(job_id: str, file_bytes: bytes, index_name: str,
                         namespace: str, embedding_fields: list[str]):
    """Background task that runs the upsert and updates the job store."""
    progress = _jobs[job_id]
    try:
        result = await asyncio.to_thread(
            run_pinecone_upsert,
            file_bytes=file_bytes,
            index_name=index_name,
            namespace=namespace,
            embedding_fields=embedding_fields,
            progress=progress,
        )
    except Exception as exc:
        logger.exception("Upsert job %s failed", job_id)
        progress.update(status="failed", phase="Error", error=str(exc))


@router.post("/upsert-pinecone-polling")
async def upsert_pinecone_polling(
    file: UploadFile = File(...),
    index_name: str = Form(...),
    namespace: str = Form(...),
    embedding_fields: str = Form(...),
):
    # Parse embedding_fields JSON string
    try:
        fields_list = json.loads(embedding_fields)
        if not isinstance(fields_list, list) or not all(isinstance(f, str) for f in fields_list):
            raise ValueError("embedding_fields must be a JSON array of strings.")
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"detail": "embedding_fields must be a valid JSON array, e.g. '[\"descriptor_eng\"]'."},
        )

    try:
        file_bytes = await file.read()
    except Exception as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Create job
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "accepted", "phase": "Queued", "progress_percent": 0}

    # Start background task
    asyncio.create_task(_run_upsert_job(job_id, file_bytes, index_name, namespace, fields_list))

    return {"job_id": job_id, "status": "accepted"}


@router.get("/upsert-pinecone-polling/{job_id}/status")
async def upsert_pinecone_polling_status(job_id: str):
    if job_id not in _jobs:
        return JSONResponse(status_code=404, content={"detail": f"Job '{job_id}' not found."})
    return _jobs[job_id]