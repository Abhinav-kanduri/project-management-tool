import logging
import os

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOTENV_LOADED = load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


OPENAI_API_KEY = required("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini")
OPENAI_EMBEDDING_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
)
OPENAI_EMBEDDING_DIMENSIONS = int(
    os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "1536")
)
DATABASE_URL = required("DATABASE_URL")
APP_ENV = os.getenv("APP_ENV", "development")
KNOWLEDGE_UPLOAD_ROOT = os.getenv("KNOWLEDGE_UPLOAD_ROOT", "data/uploads")
KNOWLEDGE_UPLOAD_MAX_BYTES = int(
    os.getenv("KNOWLEDGE_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024))
)
KNOWLEDGE_EMBEDDING_BATCH_SIZE = int(
    os.getenv("KNOWLEDGE_EMBEDDING_BATCH_SIZE", "64")
)
WORKSPACE_ENVIRONMENTS = tuple(
    value.strip()
    for value in os.getenv(
        "WORKSPACE_ENVIRONMENTS", "production,staging"
    ).split(",")
    if value.strip()
)
ENABLE_APPLICATION_DATA_RESET = os.getenv("ENABLE_APPLICATION_DATA_RESET", "false").lower() == "true"
ADMIN_RESET_TOKEN = os.getenv("ADMIN_RESET_TOKEN")

logger.info(
    "Environment configuration loaded: dotenv_loaded=%s app_env=%s "
    "openai_chat_model=%s openai_embedding_model=%s "
    "openai_embedding_dimensions=%s openai_api_key_configured=%s "
    "database_url_configured=%s application_data_reset_enabled=%s "
    "admin_reset_token_configured=%s",
    DOTENV_LOADED,
    APP_ENV,
    OPENAI_CHAT_MODEL,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_DIMENSIONS,
    bool(OPENAI_API_KEY),
    bool(DATABASE_URL),
    ENABLE_APPLICATION_DATA_RESET,
    bool(ADMIN_RESET_TOKEN),
)
