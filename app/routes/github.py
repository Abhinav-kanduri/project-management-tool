from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
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
from app.github_summary.github_url import InvalidGitHubUrl
from app.github_summary.models import (
    ChunkInspectionResponse,
    RepositorySummaryRequest,
    RepositorySummaryResponse,
    SummarySearchRequest,
    SummarySearchResponse,
)
from app.github_summary.service import OpenAISummaryError, RepositorySummaryService


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
    request: SummarySearchRequest,
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


@router.post("/summary", response_model=RepositorySummaryResponse)
async def summarize_github_repository(
    request: RepositorySummaryRequest,
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
