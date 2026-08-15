from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class RepositorySummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_url: str = Field(min_length=20, max_length=500)
    branch: str | None = Field(default=None, min_length=1, max_length=255)
    force_refresh: bool = False

    @field_validator("repository_url", "branch")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("Control characters are not accepted")
        return value


class RepositoryBranchOption(BaseModel):
    name: str
    commit_sha: str | None = None
    protected: bool = False


class RepositoryBranchOptionsResponse(BaseModel):
    branches: list[RepositoryBranchOption]
    refreshed_at: datetime


class ComponentSummary(BaseModel):
    name: str
    paths: list[str]
    responsibility: str


class ApiEndpointSummary(BaseModel):
    method: str
    path: str
    purpose: str
    source_file: str | None


class BatchSummary(BaseModel):
    files_reviewed: list[str]
    overview: str
    components: list[ComponentSummary]
    api_endpoints: list[ApiEndpointSummary]
    dependencies: list[str]
    data_and_storage: list[str]
    processing_flow: list[str]
    setup_observations: list[str]
    strengths: list[str]
    risks: list[str]
    evidence_files: list[str]


class RepositorySummary(BaseModel):
    title: str
    executive_summary: str
    problem_statement: str
    primary_capabilities: list[str]
    architecture: list[str]
    technology_stack: list[str]
    key_components: list[ComponentSummary]
    api_endpoints: list[ApiEndpointSummary]
    data_and_storage: list[str]
    request_or_processing_flow: list[str]
    setup_and_run: list[str]
    strengths: list[str]
    risks_and_gaps: list[str]
    recommended_next_steps: list[str]
    evidence_files: list[str]


class RepositoryIdentity(BaseModel):
    owner: str
    name: str
    full_name: str
    url: str
    visibility: str | None
    description: str | None
    default_branch: str
    analyzed_ref: str
    commit_sha: str | None
    language_bytes: dict[str, int]
    stars: int
    forks: int
    open_issues: int
    archived: bool

    @computed_field
    @property
    def repository_url(self) -> str:
        return self.url

    @computed_field
    @property
    def repository_full_name(self) -> str:
        return self.full_name

    @computed_field
    @property
    def branch(self) -> str:
        return self.analyzed_ref


class AnalysisStatistics(BaseModel):
    archive_bytes: int
    discovered_files: int
    analyzed_files: int
    skipped_files: int
    analyzed_characters: int
    batches: int
    cache_hit: bool
    summary_chunks: int = 0
    embedded_chunks: int = 0


class SummaryArtifact(BaseModel):
    document_id: UUID
    markdown_file: str
    chunks_file: str
    manifest_file: str
    markdown_download_url: str
    chunks_url: str
    content_sha256: str
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    indexed_at: datetime


class RepositorySummaryResponse(BaseModel):
    status: Literal["completed"] = "completed"
    generated_at: datetime
    duration_seconds: float
    repository: RepositoryIdentity
    analysis: AnalysisStatistics
    summary: RepositorySummary
    summary_markdown: str
    model: str
    artifact: SummaryArtifact | None = None


class ChunkInspectionItem(BaseModel):
    chunk_id: UUID
    chunk_index: int
    heading_path: list[str]
    section_title: str | None
    start_line: int
    end_line: int
    token_count: int
    content: str


class ChunkInspectionResponse(BaseModel):
    document_id: UUID
    total: int
    offset: int
    limit: int
    chunks: list[ChunkInspectionItem]


class SummarySearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "title": "Search by summary document",
                    "required": ["document_id"],
                    "not": {"required": ["repository_url"]},
                },
                {
                    "title": "Search by repository",
                    "required": ["repository_url"],
                    "not": {"required": ["document_id"]},
                },
            ]
        },
    )

    document_id: UUID | None = None
    repository_url: str | None = Field(default=None, min_length=20, max_length=500)
    branch: str | None = Field(default=None, min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_target(self) -> SummarySearchRequest:
        if self.document_id is None and self.repository_url is None:
            raise ValueError("Either document_id or repository_url is required")
        if self.document_id is not None and self.repository_url is not None:
            raise ValueError("Use either document_id or repository_url, not both")
        if self.branch is not None and self.repository_url is None:
            raise ValueError("branch can only be used with repository_url")
        return self


class SummarySearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    repository_full_name: str
    branch: str
    commit_sha: str
    chunk_index: int
    score: float
    heading_path: list[str]
    section_title: str | None
    start_line: int
    end_line: int
    content: str


class SummarySearchResponse(BaseModel):
    query: str
    score_calculation: str = "cosine_similarity = 1 - pgvector_cosine_distance"
    results: list[SummarySearchResult]


class SummaryDocumentReference(BaseModel):
    document_id: UUID
    repository_url: str
    repository_full_name: str
    branch: str
    commit_sha: str
    title: str
    generated_at: datetime
    indexed_at: datetime | None = None
    chunk_count: int


class LatestSummaryResponse(BaseModel):
    summary: SummaryDocumentReference | None = None
