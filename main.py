import os
import logging
from fastapi import FastAPI
from config import Config

logging.basicConfig(
    level=Config.LOG_LEVEL.upper(),
    format="%(asctime)s | %(levelname)s | %(message)s"
)

app = FastAPI(
    title=Config.APP_NAME,
    version=Config.VERSION
)

@app.get("/")
async def root():
    return {
        "service": Config.APP_NAME,
        "env": Config.APP_ENV
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "env": Config.APP_ENV
    }

@app.get("/version")
async def version():
    return {
        "name": Config.APP_NAME,
        "version": Config.VERSION,
        "env": Config.APP_ENV
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=Config.LOG_LEVEL.lower()
    )