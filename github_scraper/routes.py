import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings


settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("github_repository_summary")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Accepts a GitHub repository URL, downloads a secure repository snapshot, "
        "analyzes source and documentation files, and returns a structured AI summary."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request_id,
    )
    return response


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "summary_endpoint": "/api/v1/github/summary",
    }
