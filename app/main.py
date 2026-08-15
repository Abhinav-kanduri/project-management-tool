from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.neo4j_client import close_neo4j_client
from app.github_summary.errors import SummaryApiError
from app.github_summary.indexing import SummaryIndexingService
from app.github_summary.settings import GitHubSummarySettings
from app.routes.chat import router as chat_router
from app.routes.deletion import router as deletion_router
from app.routes.generation import router as generation_router
from app.routes.graph import router as graph_router
from app.routes.impact_contract import router as impact_analysis_router
from app.routes.impact_selectors import router as impact_selectors_router
from app.routes.github import router as github_router
from app.routes.knowledge_base import router as knowledge_base_router
from app.routes.workspace import router as workspace_router
from app.services.graph_rag import close_langchain_resources


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_langchain_resources()
    close_neo4j_client()


app = FastAPI(title="ReleaseLens API", lifespan=lifespan)
app.include_router(generation_router)
app.include_router(deletion_router)
app.include_router(workspace_router)
app.include_router(chat_router)
app.include_router(knowledge_base_router)
app.include_router(graph_router)
app.include_router(impact_analysis_router)
app.include_router(impact_selectors_router)
app.include_router(github_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(SummaryApiError)
async def summary_api_error_handler(
    _: Request, exc: SummaryApiError
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({
            "error": {
                "code": "REQUEST_VALIDATION_FAILED",
                "message": "The request did not pass validation.",
                "details": {"errors": exc.errors()},
            }
        }),
    )


@app.get("/", include_in_schema=False)
async def workspace() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse("app/static/favicon.svg", media_type="image/svg+xml")


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    service = SummaryIndexingService(GitHubSummarySettings())
    try:
        return await service.health()
    finally:
        await service.aclose()
