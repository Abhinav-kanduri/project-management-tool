from __future__ import annotations

import asyncio
import logging
import time

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.github_summary.errors import EmbeddingGenerationError
from app.github_summary.indexing_models import MarkdownChunk
from app.github_summary.settings import GitHubSummarySettings


logger = logging.getLogger(__name__)
RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)


def embedding_input(chunk: MarkdownChunk) -> str:
    section = " > ".join(chunk.heading_path) or chunk.section_title or "Unsectioned"
    return (
        f"Repository: {chunk.repository_full_name}\n"
        f"Branch: {chunk.branch}\n"
        f"Commit: {chunk.commit_sha}\n"
        f"Document: {chunk.source_file}\n"
        f"Section: {section}\n"
        f"Lines: {chunk.start_line}-{chunk.end_line}\n\n"
        f"{chunk.content}"
    )


class EmbeddingService:
    def __init__(self, settings: GitHubSummarySettings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.embedding_timeout_seconds,
            max_retries=0,
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def embed_chunks(self, chunks: list[MarkdownChunk]) -> list[MarkdownChunk]:
        embedded: list[MarkdownChunk] = []
        for start in range(0, len(chunks), self._settings.embedding_batch_size):
            batch = chunks[start : start + self._settings.embedding_batch_size]
            logger.info(
                "embedding_batch_started chunk_count=%s batch_start=%s model=%s",
                len(batch),
                start,
                self._settings.embedding_model,
            )
            started = time.perf_counter()
            vectors = await self._embed([embedding_input(chunk) for chunk in batch])
            embedded.extend(
                chunk.model_copy(update={"embedding": vector})
                for chunk, vector in zip(batch, vectors)
            )
            logger.info(
                "embedding_batch_completed chunk_count=%s batch_start=%s duration_ms=%.2f",
                len(batch),
                start,
                (time.perf_counter() - started) * 1000,
            )
        return embedded

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self._embed([query])
        return vectors[0]

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        if not inputs or any(not item.strip() for item in inputs):
            raise EmbeddingGenerationError("Embedding inputs cannot be empty")
        last_error: Exception | None = None
        for attempt in range(self._settings.embedding_max_retries + 1):
            try:
                response = await self._client.embeddings.create(
                    model=self._settings.embedding_model,
                    input=inputs,
                    dimensions=self._settings.embedding_dimensions,
                )
                ordered = sorted(response.data, key=lambda item: item.index)
                if len(ordered) != len(inputs):
                    raise EmbeddingGenerationError(
                        "Embedding response count did not match the request"
                    )
                vectors = [list(item.embedding) for item in ordered]
                if any(
                    len(vector) != self._settings.embedding_dimensions
                    for vector in vectors
                ):
                    raise EmbeddingGenerationError(
                        "Embedding response contained an unexpected vector dimension"
                    )
                return vectors
            except RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt >= self._settings.embedding_max_retries:
                    break
                await asyncio.sleep(min(2**attempt, 8))
        raise EmbeddingGenerationError(
            "Unable to generate embeddings after retrying the provider request"
        ) from last_error

