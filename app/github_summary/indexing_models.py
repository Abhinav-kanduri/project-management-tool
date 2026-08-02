from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MarkdownChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    repository_url: str
    repository_full_name: str
    branch: str
    commit_sha: str
    source_file: str = "summary.md"
    chunk_index: int
    heading_path: list[str]
    section_title: str | None
    start_line: int
    end_line: int
    token_count: int
    content_sha256: str
    content: str
    embedding_model: str
    embedding_dimensions: int
    created_at: datetime
    embedding: list[float] | None = None


class ArtifactManifest(BaseModel):
    document_id: UUID
    repository_url: str
    repository_owner: str
    repository_name: str
    repository_full_name: str
    branch: str
    commit_sha: str
    summary_file: str
    chunks_file: str
    summary_sha256: str
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    generated_at: datetime
    indexed_at: datetime
    status: str

