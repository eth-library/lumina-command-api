import os

class Config:
    APP_NAME = os.getenv("APP_NAME", "lumina-command-api")
    APP_ENV = os.getenv("APP_ENV", "local")
    VERSION = os.getenv("APP_VERSION", "0.1.0")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info")