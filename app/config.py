import os

from dotenv import load_dotenv

load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


OPENAI_API_KEY = required("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini")
DATABASE_URL = required("DATABASE_URL")
APP_ENV = os.getenv("APP_ENV", "development")
ENABLE_APPLICATION_DATA_RESET = os.getenv("ENABLE_APPLICATION_DATA_RESET", "false").lower() == "true"
ADMIN_RESET_TOKEN = os.getenv("ADMIN_RESET_TOKEN")
