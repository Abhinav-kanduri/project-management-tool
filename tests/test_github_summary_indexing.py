from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.github_summary.artifacts import ArtifactStore
from app.github_summary.chunker import MarkdownChunker
from app.github_summary.embeddings import EmbeddingService, embedding_input
from app.github_summary.errors import EmbeddingGenerationError
from app.github_summary.indexing_models import ArtifactManifest, MarkdownChunk
from app.github_summary.models import ChunkInspectionResponse, SummarySearchResponse
from app.github_summary.persistence import SummaryRepository
from app.github_summary.settings import GitHubSummarySettings
from app.routes.github import get_repository_summary_service, router


def _chunk(**updates) -> MarkdownChunk:
    values = {
        "chunk_id": uuid4(),
        "document_id": uuid4(),
        "repository_url": "https://github.com/owner/repo",
        "repository_full_name": "owner/repo",
        "branch": "main",
        "commit_sha": "a" * 40,
        "chunk_index": 0,
        "heading_path": ["Repository Summary", "Architecture Overview"],
        "section_title": "Architecture Overview",
        "start_line": 10,
        "end_line": 20,
        "token_count": 10,
        "content_sha256": hashlib.sha256(b"content").hexdigest(),
        "content": "content",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 3,
        "created_at": datetime.now(UTC),
    }
    values.update(updates)
    return MarkdownChunk(**values)


def test_markdown_chunker_preserves_headings_tables_code_lines_and_sha() -> None:
    markdown = """# Repository Summary

## Architecture Overview

Intro paragraph.

| Name | Role |
| --- | --- |
| API | Entry point |

```python
def app():
    return True
```

### Worker

Worker details.
"""
    chunks = MarkdownChunker(
        embedding_model="unknown-test-model",
        target_tokens=100,
        overlap_tokens=10,
        min_tokens=1,
    ).chunk(markdown)

    architecture = next(item for item in chunks if item.section_title == "Architecture Overview")
    worker = next(item for item in chunks if item.section_title == "Worker")
    assert architecture.heading_path == ("Repository Summary", "Architecture Overview")
    assert worker.heading_path == ("Repository Summary", "Architecture Overview", "Worker")
    assert "| --- | --- |" in architecture.content
    assert architecture.content.count("```") == 2
    assert architecture.start_line == 3
    assert architecture.end_line == 14
    assert architecture.content_sha256 == hashlib.sha256(architecture.content.encode()).hexdigest()


def test_chunker_splits_oversized_section_with_overlap() -> None:
    paragraphs = [f"Paragraph {index} " + ("word " * 35) for index in range(8)]
    markdown = "# Repository Summary\n\n## Details\n\n" + "\n\n".join(paragraphs)
    chunks = MarkdownChunker(
        embedding_model="unknown-test-model",
        target_tokens=80,
        overlap_tokens=20,
        min_tokens=1,
    ).chunk(markdown)
    details = [item for item in chunks if item.section_title == "Details"]
    assert len(details) > 1
    assert set(details[0].content.split()) & set(details[1].content.split())
    assert all(item.token_count <= 100 for item in details)


def test_embedding_input_adds_trace_context() -> None:
    value = embedding_input(_chunk())
    assert "Repository: owner/repo" in value
    assert "Section: Repository Summary > Architecture Overview" in value
    assert "Lines: 10-20" in value
    assert value.endswith("content")


def test_embedding_batching_and_dimension_validation() -> None:
    settings = GitHubSummarySettings(
        openai_api_key="test",
        database_enabled=False,
        embedding_dimensions=3,
        embedding_batch_size=2,
    )
    service = EmbeddingService(settings)

    class FakeEmbeddings:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                data=[SimpleNamespace(index=index, embedding=[0.1, 0.2, 0.3]) for index, _ in enumerate(kwargs["input"])]
            )

    fake = FakeEmbeddings()
    service._client = SimpleNamespace(embeddings=fake, close=lambda: None)
    result = asyncio.run(service.embed_chunks([_chunk(chunk_index=i) for i in range(5)]))
    assert fake.calls == 3
    assert all(item.embedding == [0.1, 0.2, 0.3] for item in result)

    async def invalid_create(**_kwargs):
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1])])

    service._client = SimpleNamespace(embeddings=SimpleNamespace(create=invalid_create))
    with pytest.raises(EmbeddingGenerationError):
        asyncio.run(service.embed_query("query"))


def test_atomic_artifacts_jsonl_and_manifest(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    paths = store.paths("owner", "repo", "a" * 40)
    markdown_hash = store.write_markdown(paths.markdown, "# Summary\n")
    chunk = _chunk(embedding=[0.1, 0.2, 0.3])
    store.write_chunks(paths.chunks, [chunk])
    manifest = ArtifactManifest(
        document_id=chunk.document_id,
        repository_url=chunk.repository_url,
        repository_owner="owner",
        repository_name="repo",
        repository_full_name=chunk.repository_full_name,
        branch=chunk.branch,
        commit_sha=chunk.commit_sha,
        summary_file="summary.md",
        chunks_file="summary.chunks.jsonl",
        summary_sha256=markdown_hash,
        chunk_count=1,
        embedding_model=chunk.embedding_model,
        embedding_dimensions=chunk.embedding_dimensions,
        generated_at=chunk.created_at,
        indexed_at=chunk.created_at,
        status="completed",
    )
    store.write_manifest(paths.manifest, manifest)

    assert paths.markdown.read_text(encoding="utf-8") == "# Summary\n"
    jsonl_lines = paths.chunks.read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == 1
    assert json.loads(jsonl_lines[0])["embedding"] == [0.1, 0.2, 0.3]
    assert json.loads(paths.manifest.read_text(encoding="utf-8"))["chunk_count"] == 1
    assert not list(paths.directory.glob("*.tmp"))


def test_retrieval_routes_and_search_route_order(tmp_path: Path) -> None:
    document_id = uuid4()
    markdown = tmp_path / "summary.md"
    markdown.write_text("# Repository Summary\n", encoding="utf-8")

    class FakeService:
        async def markdown_path(self, _document_id):
            return markdown

        async def chunks(self, _document_id, *, offset, limit):
            return ChunkInspectionResponse(
                document_id=document_id, total=0, offset=offset, limit=limit, chunks=[]
            )

        async def search(self, request):
            return SummarySearchResponse(query=request.query, results=[])

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_summary_service] = lambda: FakeService()
    client = TestClient(app)

    assert client.get(f"/api/v1/github/summary/{document_id}/markdown").status_code == 200
    chunks = client.get(f"/api/v1/github/summary/{document_id}/chunks?offset=2&limit=5")
    assert chunks.json()["offset"] == 2
    search = client.post(
        "/api/v1/github/summary/search",
        json={"document_id": str(document_id), "query": "architecture", "top_k": 3},
    )
    assert search.status_code == 200
    assert search.json()["results"] == []


def test_chunk_index_transaction_orders_replace_before_complete(monkeypatch) -> None:
    statements: list[str] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters=None):
            statements.append(" ".join(statement.split()).lower())

    class FakeConnection:
        commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            self.commits += 1

    connection = FakeConnection()
    monkeypatch.setattr(
        "app.github_summary.persistence.get_connection", lambda: connection
    )
    chunk = _chunk(embedding=[0.1, 0.2, 0.3])
    SummaryRepository().replace_chunks_and_complete(
        document_id=chunk.document_id,
        chunks=[chunk],
        indexed_at=chunk.created_at,
        response_payload={"status": "completed"},
    )

    assert statements[0].startswith("delete from github_repository_summary_chunks")
    assert statements[1].startswith("insert into github_repository_summary_chunks")
    assert "set status = 'completed'" in statements[2]
    assert connection.commits == 1


def test_health_endpoint_reports_dependency_fields(monkeypatch) -> None:
    class FakeIndexingService:
        def __init__(self, _settings):
            pass

        async def health(self):
            return {
                "status": "ok",
                "database": "connected",
                "pgvector": "available",
                "github_configuration": "configured",
                "summary_model": "configured",
                "embedding_model": "configured",
                "artifact_directory": "available",
            }

        async def aclose(self):
            return None

    monkeypatch.setattr("app.main.SummaryIndexingService", FakeIndexingService)
    from app.main import app as main_app

    response = TestClient(main_app).get("/health")
    assert response.status_code == 200
    assert response.json()["pgvector"] == "available"
    assert "github_configuration" in response.json()
