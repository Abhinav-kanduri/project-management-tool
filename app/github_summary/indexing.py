from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.github_summary.artifacts import ArtifactStore
from app.github_summary.chunker import MarkdownChunker
from app.github_summary.embeddings import EmbeddingService
from app.github_summary.errors import (
    EmbeddingGenerationError,
    SummaryArtifactError,
    SummaryDatabaseError,
)
from app.github_summary.github_url import parse_github_repository_url
from app.github_summary.indexing_models import ArtifactManifest, MarkdownChunk
from app.github_summary.models import (
    ChunkInspectionResponse,
    RepositorySummaryResponse,
    SummaryArtifact,
    SummarySearchRequest,
    SummarySearchResponse,
)
from app.github_summary.persistence import SummaryRepository
from app.github_summary.security import redact_secrets
from app.github_summary.settings import GitHubSummarySettings


logger = logging.getLogger(__name__)


class SummaryIndexingService:
    def __init__(self, settings: GitHubSummarySettings) -> None:
        self.settings = settings
        self.artifacts = ArtifactStore(settings.output_directory)
        self.repository = SummaryRepository()
        self.chunker = MarkdownChunker(
            embedding_model=settings.embedding_model,
            target_tokens=settings.summary_chunk_target_tokens,
            overlap_tokens=settings.summary_chunk_overlap_tokens,
            min_tokens=settings.summary_chunk_min_tokens,
        )
        self.embeddings = EmbeddingService(settings)

    async def aclose(self) -> None:
        await self.embeddings.aclose()

    async def cached_response(
        self,
        *,
        repository_full_name: str,
        branch: str,
        commit_sha: str,
    ) -> RepositorySummaryResponse | None:
        if not self.settings.database_enabled:
            return None
        row = await asyncio.to_thread(
            self.repository.find_completed,
            repository_full_name=repository_full_name,
            branch=branch,
            commit_sha=commit_sha,
            summary_format_version=self.settings.summary_format_version,
            summary_model=self.settings.openai_model,
            embedding_model=self.settings.embedding_model,
            embedding_dimensions=self.settings.embedding_dimensions,
        )
        if not row:
            return None
        for field in ("markdown_path", "chunks_path", "manifest_path"):
            value = row.get(field)
            if not value:
                return None
            try:
                if not self.artifacts.resolve_stored_path(str(value)).is_file():
                    return None
            except SummaryArtifactError:
                return None
        try:
            response = RepositorySummaryResponse.model_validate(row["response_payload"])
        except (KeyError, ValidationError, TypeError):
            return None
        return response.model_copy(
            update={
                "analysis": response.analysis.model_copy(update={"cache_hit": True})
            }
        )

    async def index(
        self,
        response: RepositorySummaryResponse,
    ) -> RepositorySummaryResponse:
        if not self.settings.database_enabled:
            return response
        commit_sha = response.repository.commit_sha
        if not commit_sha:
            raise SummaryArtifactError("A resolved commit SHA is required for indexing")

        started = time.perf_counter()
        document_id = uuid4()
        paths = self.artifacts.paths(
            response.repository.owner,
            response.repository.name,
            commit_sha,
        )
        summary_sha256 = self.artifacts.write_markdown(
            paths.markdown, response.summary_markdown
        )
        logger.info(
            "summary_markdown_written repository_full_name=%s branch=%s commit_sha=%s document_id=%s status=SUMMARY_GENERATED",
            response.repository.full_name,
            response.repository.analyzed_ref,
            commit_sha,
            document_id,
        )

        document_id = await asyncio.to_thread(
            self.repository.upsert_generated,
            document_id=document_id,
            repository_url=response.repository.url,
            repository_owner=response.repository.owner,
            repository_name=response.repository.name,
            repository_full_name=response.repository.full_name,
            branch=response.repository.analyzed_ref,
            commit_sha=commit_sha,
            markdown_path=self.artifacts.relative_path(paths.markdown),
            chunks_path=self.artifacts.relative_path(paths.chunks),
            manifest_path=self.artifacts.relative_path(paths.manifest),
            summary_sha256=summary_sha256,
            summary_format_version=self.settings.summary_format_version,
            summary_model=self.settings.openai_model,
            embedding_model=self.settings.embedding_model,
            embedding_dimensions=self.settings.embedding_dimensions,
            generated_at=response.generated_at,
            response_payload=response.model_dump(mode="json"),
        )

        try:
            await asyncio.to_thread(self.repository.set_status, document_id, "CHUNKING")
            drafts = await asyncio.to_thread(
                self.chunker.chunk, response.summary_markdown
            )
            if not drafts:
                raise SummaryArtifactError("The generated Markdown produced no chunks")
            created_at = datetime.now(UTC)
            chunks = [
                MarkdownChunk(
                    chunk_id=uuid4(),
                    document_id=document_id,
                    repository_url=response.repository.url,
                    repository_full_name=response.repository.full_name,
                    branch=response.repository.analyzed_ref,
                    commit_sha=commit_sha,
                    chunk_index=index,
                    heading_path=list(draft.heading_path),
                    section_title=draft.section_title,
                    start_line=draft.start_line,
                    end_line=draft.end_line,
                    token_count=draft.token_count,
                    content_sha256=draft.content_sha256,
                    content=draft.content,
                    embedding_model=self.settings.embedding_model,
                    embedding_dimensions=self.settings.embedding_dimensions,
                    created_at=created_at,
                )
                for index, draft in enumerate(drafts)
            ]
            logger.info(
                "summary_chunking_completed repository_full_name=%s branch=%s commit_sha=%s document_id=%s chunk_count=%s status=CHUNKING",
                response.repository.full_name,
                response.repository.analyzed_ref,
                commit_sha,
                document_id,
                len(chunks),
            )

            await asyncio.to_thread(self.repository.set_status, document_id, "EMBEDDING")
            chunks = await self.embeddings.embed_chunks(chunks)
            self.artifacts.write_chunks(paths.chunks, chunks)
            await asyncio.to_thread(self.repository.set_status, document_id, "INDEXING")
            indexed_at = datetime.now(UTC)
            artifact = SummaryArtifact(
                document_id=document_id,
                markdown_file=self.artifacts.relative_path(paths.markdown),
                chunks_file=self.artifacts.relative_path(paths.chunks),
                manifest_file=self.artifacts.relative_path(paths.manifest),
                markdown_download_url=f"/api/v1/github/summary/{document_id}/markdown",
                chunks_url=f"/api/v1/github/summary/{document_id}/chunks",
                content_sha256=summary_sha256,
                chunk_count=len(chunks),
                embedding_model=self.settings.embedding_model,
                embedding_dimensions=self.settings.embedding_dimensions,
                indexed_at=indexed_at,
            )
            completed = response.model_copy(
                update={
                    "analysis": response.analysis.model_copy(
                        update={
                            "summary_chunks": len(chunks),
                            "embedded_chunks": len(chunks),
                        }
                    ),
                    "artifact": artifact,
                }
            )
            manifest = ArtifactManifest(
                document_id=document_id,
                repository_url=response.repository.url,
                repository_owner=response.repository.owner,
                repository_name=response.repository.name,
                repository_full_name=response.repository.full_name,
                branch=response.repository.analyzed_ref,
                commit_sha=commit_sha,
                summary_file=paths.markdown.name,
                chunks_file=paths.chunks.name,
                summary_sha256=summary_sha256,
                chunk_count=len(chunks),
                embedding_model=self.settings.embedding_model,
                embedding_dimensions=self.settings.embedding_dimensions,
                generated_at=response.generated_at,
                indexed_at=indexed_at,
                status="completed",
            )
            await asyncio.to_thread(
                self.repository.replace_chunks_and_complete,
                document_id=document_id,
                chunks=chunks,
                indexed_at=indexed_at,
                response_payload=completed.model_dump(mode="json"),
            )
            self.artifacts.write_manifest(paths.manifest, manifest)
            logger.info(
                "summary_database_indexing_completed repository_full_name=%s branch=%s commit_sha=%s document_id=%s chunk_count=%s duration_ms=%.2f status=COMPLETED",
                response.repository.full_name,
                response.repository.analyzed_ref,
                commit_sha,
                document_id,
                len(chunks),
                (time.perf_counter() - started) * 1000,
            )
            return completed
        except Exception as exc:
            safe_message = redact_secrets(str(exc))[:2000]
            try:
                await asyncio.to_thread(
                    self.repository.mark_failed, document_id, safe_message
                )
            except SummaryDatabaseError:
                logger.exception(
                    "summary_failure_status_update_failed document_id=%s", document_id
                )
            logger.exception(
                "summary_processing_failed repository_full_name=%s branch=%s commit_sha=%s document_id=%s status=FAILED",
                response.repository.full_name,
                response.repository.analyzed_ref,
                commit_sha,
                document_id,
            )
            raise

    async def markdown_path(self, document_id: UUID) -> Path | None:
        row = await asyncio.to_thread(self.repository.get_document, document_id)
        if not row:
            return None
        path = self.artifacts.resolve_stored_path(row["markdown_path"])
        return path

    async def chunks(
        self, document_id: UUID, *, offset: int, limit: int
    ) -> ChunkInspectionResponse | None:
        document = await asyncio.to_thread(self.repository.get_document, document_id)
        if not document:
            return None
        total, chunks = await asyncio.to_thread(
            self.repository.list_chunks, document_id, offset=offset, limit=limit
        )
        return ChunkInspectionResponse(
            document_id=document_id,
            total=total,
            offset=offset,
            limit=limit,
            chunks=chunks,
        )

    async def search(self, request: SummarySearchRequest) -> SummarySearchResponse:
        repository_url = None
        if request.repository_url:
            repository_url = parse_github_repository_url(
                request.repository_url, allowed_hosts=self.settings.allowed_hosts
            ).canonical_url
        query_vector = await self.embeddings.embed_query(request.query)
        rows = await asyncio.to_thread(
            self.repository.semantic_search,
            query_vector=query_vector,
            document_id=request.document_id,
            repository_url=repository_url,
            branch=request.branch,
            top_k=request.top_k,
        )
        logger.info(
            "summary_semantic_search_completed document_id=%s repository_url=%s result_count=%s status=COMPLETED",
            request.document_id,
            repository_url,
            len(rows),
        )
        return SummarySearchResponse(query=request.query, results=rows)

    async def health(self) -> dict[str, str]:
        artifact_available = await asyncio.to_thread(self.artifacts.ensure_available)
        if self.settings.database_enabled:
            database, vector = await asyncio.to_thread(self.repository.health)
        else:
            database, vector = False, False
        status = (
            "ok"
            if database
            and vector
            and artifact_available
            and self.settings.github_token
            and self.settings.openai_api_key
            and self.settings.openai_model
            and self.settings.embedding_model
            else "degraded"
        )
        return {
            "status": status,
            "database": "connected" if database else "disabled_or_unavailable",
            "pgvector": "available" if vector else "disabled_or_unavailable",
            "github_configuration": "configured" if self.settings.github_token else "missing",
            "summary_model": "configured" if self.settings.openai_model else "missing",
            "embedding_model": "configured" if self.settings.embedding_model else "missing",
            "artifact_directory": "available" if artifact_available else "unavailable",
        }
