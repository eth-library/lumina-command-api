from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import StreamingResponse
import json
import io
import gzip

from app.services.transform_eth_udk import run_transform_eth_udk
from app.transformers.eth_udk.step8_json_to_csv import transform as step8

router = APIRouter(prefix="/commands", tags=["commands"])

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