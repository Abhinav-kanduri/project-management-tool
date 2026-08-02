import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOTENV_LOADED = load_dotenv(PROJECT_ROOT / ".env")
NEO4J_DOTENV_LOADED = load_dotenv(
    PROJECT_ROOT / "infra" / "neo4j" / ".env", override=False
)


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
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
NEO4J_VECTOR_INDEX = os.getenv("NEO4J_VECTOR_INDEX", "document_chunk_embedding")
NEO4J_ENABLED = bool(NEO4J_PASSWORD)

logger.info(
    "Environment configuration loaded: dotenv_loaded=%s app_env=%s "
    "openai_chat_model=%s openai_embedding_model=%s "
    "openai_embedding_dimensions=%s openai_api_key_configured=%s "
    "database_url_configured=%s neo4j_configured=%s application_data_reset_enabled=%s "
    "admin_reset_token_configured=%s",
    DOTENV_LOADED,
    APP_ENV,
    OPENAI_CHAT_MODEL,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_DIMENSIONS,
    bool(OPENAI_API_KEY),
    bool(DATABASE_URL),
    NEO4J_ENABLED,
    ENABLE_APPLICATION_DATA_RESET,
    bool(ADMIN_RESET_TOKEN),
)
