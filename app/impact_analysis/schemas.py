from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.impact_analysis.enums import (
    AnalysisStage,
    EvidenceDirection,
    EvidenceType,
    FindingStatus,
    GeneratedChangeStatus,
    GraphNodeType,
    GraphRelationshipType,
    ImpactCategory,
    PredicateResult,
    ReasonCode,
    RequirementApplicability,
    RequirementType,
    RetrievalMethod,
    RunStatus,
    ScopeType,
)
from app.impact_analysis.validators import validate_status_reason


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RepositoryBranch(StrictModel):
    name: str
    commit_sha: str | None = None
    protected: bool = False
    snapshot_id: UUID | None = None
    sync_status: str | None = None
    last_synced_at: datetime | None = None


class RepositoryBranchListResponse(StrictModel):
    branches: list[RepositoryBranch]
    refreshed_at: datetime


class RepositoryBranchSyncRequest(StrictModel):
    branch: str = Field(min_length=1, max_length=255)
    force_refresh: bool = False

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("A valid branch name is required")
        return value


class RepositoryBranchSyncResponse(StrictModel):
    snapshot_id: UUID
    branch: str
    commit_sha: str
    status: str
    cache_hit: bool
    synced_at: datetime
    discovered_files: int
    indexed_files: int
    skipped_files: int
    coverage_percent: float


class RepositoryUnlinkResponse(StrictModel):
    unlinked: bool
    project_repository_id: UUID
    project_id: UUID
    repository_full_name: str



class StartAnalysisRequest(StrictModel):
    product_space_id: UUID
    project_id: UUID
    release_id: UUID | None = None
    scope_type: ScopeType
    scope_id: UUID
    project_repository_id: UUID
    ref: str | None = Field(default=None, min_length=1, max_length=255)
    force_repository_refresh: bool = False
    client_request_id: UUID

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("Repository ref cannot contain control characters")
        return value


class ScopeSummary(StrictModel):
    type: ScopeType
    id: UUID
    key: str
    title: str


class RepositorySummary(StrictModel):
    project_repository_id: UUID
    repository_id: UUID
    name: str
    full_name: str
    branch: str
    commit_sha: str


class StatusCounts(StrictModel):
    present: int = Field(default=0, ge=0)
    partial: int = Field(default=0, ge=0)
    missing: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


class AnalysisRunResponse(StrictModel):
    run_id: UUID
    status: RunStatus
    stage: AnalysisStage
    progress_percent: int = Field(ge=0, le=100)
    message: str | None = None
    scope: ScopeSummary | None = None
    repository: RepositorySummary | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    counts: StatusCounts = Field(default_factory=StatusCounts)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class ExpectedPredicate(StrictModel):
    predicate_id: str = Field(pattern=r"^PRED-[A-Z0-9_-]+$")
    predicate_type: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=500)
    object: str | None = Field(default=None, max_length=500)
    mandatory: bool = True
    result: PredicateResult | None = None


class RequirementProvenance(StrictModel):
    source_type: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=500)
    source_locator: dict[str, Any] = Field(default_factory=dict)


class AtomicRequirement(StrictModel):
    requirement_id: UUID | None = None
    requirement_key: str = Field(pattern=r"^REQ-[0-9]{3,}$")
    text: str = Field(min_length=5, max_length=4000)
    type: RequirementType
    applicability: RequirementApplicability = (
        RequirementApplicability.STATICALLY_VERIFIABLE
    )
    weight: float = Field(gt=0, le=1)
    provenance: list[RequirementProvenance] = Field(min_length=1)
    expected_predicates: list[ExpectedPredicate] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_predicates(self) -> AtomicRequirement:
        identifiers = [item.predicate_id for item in self.expected_predicates]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Expected predicate IDs must be unique")
        return self


class EvidenceRecord(StrictModel):
    evidence_id: UUID
    requirement_id: UUID
    type: EvidenceType
    direction: EvidenceDirection
    retrieval_method: RetrievalMethod
    repository: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    symbol: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1, max_length=10_000)
    excerpt: str | None = Field(default=None, max_length=30_000)
    rank: int | None = Field(default=None, ge=1)
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_span(self) -> EvidenceRecord:
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("Source evidence requires both start_line and end_line")
        if self.start_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line cannot be before start_line")
        if self.type in {EvidenceType.SOURCE_CODE, EvidenceType.TEST}:
            if not self.file_path or not self.commit_sha:
                raise ValueError("Source/test evidence requires file_path and commit_sha")
        return self


class ImpactStatement(StrictModel):
    category: ImpactCategory
    summary: str = Field(min_length=1, max_length=4000)
    conditional: bool = False
    evidence_ids: list[UUID] = Field(default_factory=list)


class LLMComparisonCandidate(StrictModel):
    requirement_id: UUID
    candidate_status: FindingStatus
    confidence: float = Field(ge=0, le=1)
    present_summary: str = Field(default="", max_length=10_000)
    missing_summary: str = Field(default="", max_length=10_000)
    reason_code: ReasonCode
    technical_reason: str = Field(min_length=1, max_length=10_000)
    explanation: str = Field(min_length=1, max_length=10_000)
    impacts: list[ImpactStatement] = Field(default_factory=list)
    recommendation: str = Field(min_length=1, max_length=10_000)
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_reason_match(self) -> LLMComparisonCandidate:
        validate_status_reason(self.candidate_status, self.reason_code)
        return self


class FindingResponse(StrictModel):
    finding_id: UUID
    requirement_id: UUID
    requirement: str
    status: FindingStatus
    what_present: str
    what_missing: str
    reason_code: ReasonCode
    technical_reason: str
    explanation: str
    impacts: list[ImpactStatement]
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    weight: float = Field(gt=0, le=1)
    completion: float | None = Field(default=None, ge=0, le=1)
    score_contribution: float | None = Field(default=None, ge=0, le=100)
    evidence_count: int = Field(ge=0)
    code_generation_available: bool

    @model_validator(mode="after")
    def status_reason_match(self) -> FindingResponse:
        validate_status_reason(self.status, self.reason_code)
        return self


class GraphNode(StrictModel):
    id: str = Field(min_length=1, max_length=1000)
    type: GraphNodeType
    label: str = Field(min_length=1, max_length=500)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(StrictModel):
    id: str = Field(min_length=1, max_length=1000)
    type: GraphRelationshipType
    source: str
    target: str
    confidence: float = Field(default=1, ge=0, le=1)
    inferred: bool = False
    evidence_ids: list[UUID] = Field(default_factory=list)


class GraphResponse(StrictModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @model_validator(mode="after")
    def validate_edge_endpoints(self) -> GraphResponse:
        node_ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"Graph edge {edge.id} references an unknown node")
            if edge.inferred and not edge.evidence_ids:
                raise ValueError("Inferred graph edges require evidence IDs")
        return self


class GeneratedChangeResponse(StrictModel):
    change_id: UUID
    finding_id: UUID
    status: GeneratedChangeStatus
    base_commit_sha: str
    files: list[str] = Field(default_factory=list)
    patch: str | None = None
    explanation: str | None = None
    tests_proposed: list[str] = Field(default_factory=list)
