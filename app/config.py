import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    APP_NAME = os.getenv("APP_NAME", "lumina-command-api")
    APP_ENV = os.getenv("APP_ENV", "local")
    VERSION = os.getenv("APP_VERSION", "0.1.0")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
    INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

    # Lumina Engine — Prefect server (read-only, unauthenticated, no secret to protect)
    PREFECT_API_URL = os.getenv("PREFECT_API_URL", "http://lumina-box01.ethz.ch:4200/api")