from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes.generation import router as generation_router
from app.routes.workspace import router as workspace_router

app = FastAPI(title="ReleaseLens API")
app.include_router(generation_router)
app.include_router(workspace_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def workspace() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse("app/static/favicon.svg", media_type="image/svg+xml")


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
