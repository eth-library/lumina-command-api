import os
import logging
from fastapi import FastAPI
from app.config import Config
from app.routers.commands import router as commands_router
from app.routers.pipeline import router as pipeline_router

logging.basicConfig(
    level=Config.LOG_LEVEL.upper(),
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ✅ ZUERST app definieren
app = FastAPI(
    title=Config.APP_NAME,
    version=Config.VERSION
)

# ✅ DANN Router registrieren
app.include_router(commands_router)
app.include_router(pipeline_router)


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
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level=Config.LOG_LEVEL.lower()
    )