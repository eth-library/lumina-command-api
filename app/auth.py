from fastapi import Header, HTTPException
from app.config import Config


async def verify_api_key(x_api_key: str | None = Header(default=None)):
    if not Config.INTERNAL_API_KEY:
        raise HTTPException(status_code=500, detail="INTERNAL_API_KEY not configured.")
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key.")
    if x_api_key != Config.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key.")
