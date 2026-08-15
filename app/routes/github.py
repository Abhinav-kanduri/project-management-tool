from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import FileResponse, Response
from openai import OpenAIError

from app.github_summary.archive import UnsafeArchiveError
from app.github_summary.catalog import (
    GitHubConfigurationError,
    GitHubRepositoryCatalogService,
    RepositoryScopeError,
)
from app.github_summary.catalog_models import (
    GitHubRepositoryImportRequest,
    GitHubRepositoryListResponse,
    ImportedGitHubRepository,
    ImportedGitHubRepositoryListResponse,
)
from app.github_summary.errors import (
    EmbeddingGenerationError,
    SummaryApiError,
    SummaryArtifactError,
    SummaryDatabaseError,
)
from app.github_summary.github_client import GitHubApiError
from app.github_summary.github_client import GitHubClient
from app.github_summary.github_url import InvalidGitHubUrl, parse_github_repository_url
from app.github_summary.exports import (
    build_summary_docx,
    build_summary_pdf,
    export_filename,
)
from app.github_summary.models import (
    ChunkInspectionResponse,
    LatestSummaryResponse,
    RepositoryBranchOption,
    RepositoryBranchOptionsResponse,
    RepositorySummaryRequest,
    RepositorySummaryResponse,
    SummarySearchRequest,
    SummarySearchResponse,
)
from app.github_summary.service import OpenAISummaryError, RepositorySummaryService
from app.github_summary.settings import GitHubSummarySettings


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/github", tags=["GitHub Repository Summary"])


async def get_repository_summary_service() -> AsyncIterator[RepositorySummaryService]:
    service = RepositorySummaryService()
    try:
        yield service
    finally:
        await service.aclose()


SummaryService = Annotated[RepositorySummaryService, Depends(get_repository_summary_service)]


def get_repository_catalog_service() -> GitHubRepositoryCatalogService:
    return GitHubRepositoryCatalogService()


CatalogService = Annotated[
    GitHubRepositoryCatalogService, Depends(get_repository_catalog_service)
]


@router.get("/summary/latest", response_model=LatestSummaryResponse)
async def latest_repository_summary(
    service: SummaryService,
    repository_url: Annotated[str, Query(min_length=20, max_length=500)],
    branch: Annotated[str, Query(min_length=1, max_length=255)],
) -> LatestSummaryResponse:
    try:
        return await service.latest_summary(
            repository_url=repository_url,
            branch=branch,
        )
    except InvalidGitHubUrl as exc:
        raise SummaryApiError(400, "INVALID_GITHUB_URL", str(exc)) from exc
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503,
            "DATABASE_UNAVAILABLE",
            "Repository summary discovery is unavailable.",
        ) from exc


@router.get("/repositories", response_model=GitHubRepositoryListResponse)
async def list_github_repositories(
    service: CatalogService,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 100,
    project_id: UUID | None = None,
) -> GitHubRepositoryListResponse:
    try:
        return await service.list_repositories(
            page=page, per_page=per_page, project_id=project_id
        )
    except GitHubConfigurationError as exc:
        raise SummaryApiError(503, "GITHUB_NOT_CONFIGURED", str(exc)) from exc
    except GitHubApiError as exc:
        _raise_catalog_github_error(exc)
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository catalog storage is unavailable."
        ) from exc


@router.get(
    "/repositories/branches",
    response_model=RepositoryBranchOptionsResponse,
    summary="List branches for a repository visible to the backend GitHub token",
)
async def list_repository_branch_options(
    repository_url: Annotated[str, Query(min_length=20, max_length=500)],
) -> RepositoryBranchOptionsResponse:
    try:
        settings = GitHubSummarySettings()
        repository = parse_github_repository_url(
            repository_url,
            allowed_hosts=settings.allowed_hosts,
        )
        async with GitHubClient(settings) as github:
            payload = await github.list_branches(repository)
        branches = [
            RepositoryBranchOption(
                name=str(item["name"]),
                commit_sha=(
                    str((item.get("commit") or {}).get("sha"))
                    if (item.get("commit") or {}).get("sha")
                    else None
                ),
                protected=bool(item.get("protected", False)),
            )
            for item in payload
            if isinstance(item, dict) and item.get("name")
        ]
        return RepositoryBranchOptionsResponse(
            branches=branches,
            refreshed_at=datetime.now(UTC),
        )
    except InvalidGitHubUrl as exc:
        raise SummaryApiError(400, "INVALID_GITHUB_URL", str(exc)) from exc
    except GitHubApiError as exc:
        _raise_catalog_github_error(exc)


@router.get(
    "/repositories/imported",
    response_model=ImportedGitHubRepositoryListResponse,
)
async def list_imported_github_repositories(
    service: CatalogService,
    product_space_id: UUID | None = None,
    project_id: UUID | None = None,
) -> ImportedGitHubRepositoryListResponse:
    try:
        return await service.list_imported(
            product_space_id=product_space_id, project_id=project_id
        )
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository catalog storage is unavailable."
        ) from exc


@router.post(
    "/repositories/import",
    response_model=ImportedGitHubRepository,
    status_code=201,
)
async def import_github_repository(
    request: GitHubRepositoryImportRequest,
    service: CatalogService,
) -> ImportedGitHubRepository:
    try:
        return await service.import_repository(
            github_repository_id=request.github_repository_id,
            product_space_id=request.product_space_id,
            project_id=request.project_id,
        )
    except GitHubConfigurationError as exc:
        raise SummaryApiError(503, "GITHUB_NOT_CONFIGURED", str(exc)) from exc
    except RepositoryScopeError as exc:
        raise SummaryApiError(422, "INVALID_PROJECT_SCOPE", str(exc)) from exc
    except GitHubApiError as exc:
        _raise_catalog_github_error(exc)
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository catalog storage is unavailable."
        ) from exc


def _raise_catalog_github_error(exc: GitHubApiError) -> None:
    status_code = exc.status_code if exc.status_code in {401, 403, 404, 429} else 502
    codes = {
        401: "GITHUB_AUTHENTICATION_FAILED",
        403: "GITHUB_PERMISSION_DENIED",
        404: "GITHUB_REPOSITORY_NOT_FOUND",
        429: "GITHUB_RATE_LIMITED",
    }
    raise SummaryApiError(
        status_code,
        codes.get(status_code, "GITHUB_PROVIDER_FAILED"),
        "GitHub could not provide the requested repository data.",
    ) from exc


@router.post("/summary/search", response_model=SummarySearchResponse)
async def search_repository_summaries(
    request: Annotated[
        SummarySearchRequest,
        Body(
            openapi_examples={
                "by_document_id": {
                    "summary": "Search one generated summary",
                    "description": (
                        "Use the document_id returned in the artifact object from "
                        "POST /api/v1/github/summary."
                    ),
                    "value": {
                        "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        "query": "How is authentication implemented?",
                        "top_k": 5,
                    },
                },
                "by_repository_url": {
                    "summary": "Search the latest summary for a repository",
                    "description": (
                        "Use repository_url instead of document_id. The optional "
                        "branch narrows the search further."
                    ),
                    "value": {
                        "repository_url": "https://github.com/octocat/Hello-World",
                        "branch": "master",
                        "query": "What are the main components?",
                        "top_k": 5,
                    },
                },
            }
        ),
    ],
    service: SummaryService,
) -> SummarySearchResponse:
    try:
        return await service.search(request)
    except InvalidGitHubUrl as exc:
        raise SummaryApiError(400, "INVALID_GITHUB_URL", str(exc)) from exc
    except EmbeddingGenerationError as exc:
        raise SummaryApiError(
            502,
            "EMBEDDING_FAILED",
            "Unable to generate an embedding for the search query.",
        ) from exc
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository summary search is unavailable."
        ) from exc


@router.post(
    "/summary/from-url",
    response_model=RepositorySummaryResponse,
    summary="Generate a repository summary from a GitHub URL",
)
@router.post("/summary", response_model=RepositorySummaryResponse)
async def summarize_github_repository(
    request: Annotated[
        RepositorySummaryRequest,
        Body(
            openapi_examples={
                "default_branch": {
                    "summary": "Summarize the default branch",
                    "value": {
                        "repository_url": (
                            "https://github.com/Abhinav-kanduri/"
                            "Customer-Support-AI-Chatbot"
                        ),
                        "force_refresh": False,
                    },
                },
                "specific_branch": {
                    "summary": "Summarize a specific branch",
                    "value": {
                        "repository_url": (
                            "https://github.com/Abhinav-kanduri/"
                            "Customer-Support-AI-Chatbot"
                        ),
                        "branch": "feature/newbranch",
                        "force_refresh": False,
                    },
                },
            }
        ),
    ],
    service: SummaryService,
) -> RepositorySummaryResponse:
    try:
        return await service.summarize(
            repository_url=request.repository_url,
            branch=request.branch,
            force_refresh=request.force_refresh,
        )
    except InvalidGitHubUrl as exc:
        raise SummaryApiError(400, "INVALID_GITHUB_URL", str(exc)) from exc
    except GitHubApiError as exc:
        status_code = exc.status_code if exc.status_code in {401, 403, 404, 429} else 502
        codes = {
            401: "GITHUB_AUTHENTICATION_FAILED",
            403: "GITHUB_PERMISSION_DENIED",
            404: "GITHUB_REPOSITORY_NOT_FOUND",
            429: "GITHUB_RATE_LIMITED",
        }
        raise SummaryApiError(
            status_code,
            codes.get(status_code, "GITHUB_PROVIDER_FAILED"),
            "GitHub could not provide the requested repository data.",
        ) from exc
    except EmbeddingGenerationError as exc:
        raise SummaryApiError(
            502,
            "EMBEDDING_FAILED",
            "Unable to generate embeddings for the repository summary.",
        ) from exc
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository summary storage is unavailable."
        ) from exc
    except SummaryArtifactError as exc:
        raise SummaryApiError(
            500, "ARTIFACT_WRITE_FAILED", "Repository summary artifacts could not be written."
        ) from exc
    except (OpenAIError, OpenAISummaryError) as exc:
        logger.exception("OpenAI repository summarization failed")
        raise SummaryApiError(
            502, "SUMMARY_MODEL_FAILED", "The AI service could not summarize the repository."
        ) from exc
    except UnsafeArchiveError as exc:
        logger.warning("Rejected unsafe GitHub archive")
        raise SummaryApiError(
            502, "UNSAFE_GITHUB_ARCHIVE", "GitHub returned an unsafe archive."
        ) from exc
    except RuntimeError as exc:
        logger.exception("Repository summarization failed")
        raise SummaryApiError(
            500, "SUMMARY_PROCESSING_FAILED", "Repository summary processing failed."
        ) from exc


@router.get("/summary/{document_id}/markdown")
async def download_repository_summary_markdown(
    document_id: UUID,
    service: SummaryService,
) -> FileResponse:
    try:
        path = await service.markdown_path(document_id)
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository summary storage is unavailable."
        ) from exc
    except SummaryArtifactError as exc:
        raise SummaryApiError(
            500, "INVALID_ARTIFACT_PATH", "The stored artifact path is invalid."
        ) from exc
    if path is None:
        raise SummaryApiError(404, "DOCUMENT_NOT_FOUND", "Summary document was not found.")
    if not path.is_file():
        raise SummaryApiError(
            404,
            "ARTIFACT_NOT_FOUND",
            "The summary record exists, but its Markdown artifact is missing.",
            document_id=str(document_id),
        )
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename="summary.md")


@router.get("/summary/{document_id}/export")
async def export_repository_summary(
    document_id: UUID,
    service: SummaryService,
    format: Annotated[Literal["docx", "pdf"], Query()] = "docx",
) -> Response:
    try:
        summary = await service.response(document_id)
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository summary storage is unavailable."
        ) from exc
    if summary is None:
        raise SummaryApiError(404, "DOCUMENT_NOT_FOUND", "Summary document was not found.")

    if format == "pdf":
        content = build_summary_pdf(summary)
        media_type = "application/pdf"
    else:
        content = build_summary_docx(summary)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    filename = export_filename(summary, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/summary/{document_id}/chunks", response_model=ChunkInspectionResponse)
async def inspect_repository_summary_chunks(
    document_id: UUID,
    service: SummaryService,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChunkInspectionResponse:
    try:
        response = await service.chunks(document_id, offset=offset, limit=limit)
    except SummaryDatabaseError as exc:
        raise SummaryApiError(
            503, "DATABASE_UNAVAILABLE", "Repository summary storage is unavailable."
        ) from exc
    if response is None:
        raise SummaryApiError(404, "DOCUMENT_NOT_FOUND", "Summary document was not found.")
    return response
