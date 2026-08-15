from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.impact_analysis.enums import RequirementApplicability, RequirementType, ScopeType
from app.impact_analysis.schemas import StrictModel


class ProjectRecord(StrictModel):
    organization_id: UUID
    product_space_id: UUID
    project_id: UUID
    project_key: str
    project_name: str
    project_description: str | None = None


class FeatureRecord(StrictModel):
    id: UUID
    feature_key: str
    title: str
    description: str | None = None
    problem_statement: str | None = None
    business_value: str | None = None
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    status: str
    priority: str
    release_id: UUID


class UserStoryRecord(StrictModel):
    id: UUID
    feature_id: UUID
    story_key: str
    title: str
    story_text: str | None = None
    status: str
    priority: str
    story_points: int | None = None
    release_id: UUID
    sprint_id: UUID | None = None


class AcceptanceCriterionRecord(StrictModel):
    id: UUID
    feature_id: UUID | None = None
    user_story_id: UUID | None = None
    given: str | None = None
    when: str | None = None
    then: str | None = None
    order: int


class RepositoryMappingRecord(StrictModel):
    project_repository_id: UUID
    repository_id: UUID
    github_repository_id: int
    full_name: str
    repository_url: str
    default_branch: str
    private: bool
    archived: bool


class RequirementPackage(StrictModel):
    project: ProjectRecord
    scope_type: ScopeType
    scope_id: UUID
    release_id: UUID | None = None
    feature: FeatureRecord
    user_story: UserStoryRecord | None = None
    acceptance_criteria: list[AcceptanceCriterionRecord]
    related_user_stories: list[UserStoryRecord] = Field(default_factory=list)
    repository: RepositoryMappingRecord

    @model_validator(mode="after")
    def validate_scope(self) -> RequirementPackage:
        if self.scope_type == ScopeType.FEATURE and self.scope_id != self.feature.id:
            raise ValueError("Feature scope ID does not match the loaded Feature")
        if self.scope_type == ScopeType.USER_STORY:
            if self.user_story is None or self.scope_id != self.user_story.id:
                raise ValueError("User Story scope requires the matching Story")
            if self.user_story.feature_id != self.feature.id:
                raise ValueError("User Story does not belong to the loaded Feature")
        if self.release_id is not None and self.feature.release_id != self.release_id:
            raise ValueError("Selected Release does not match the Feature")
        return self


class DesignEvidenceItem(StrictModel):
    document_id: str
    document_name: str
    document_type: str
    checksum: str | None = None
    chunk_id: str
    chunk_index: int
    text: str
    section_path: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    relevance_score: float = 0
    approval_basis: str


class DesignEvidencePackage(StrictModel):
    project_id: UUID
    query: str
    items: list[DesignEvidenceItem] = Field(default_factory=list)


class RequirementCandidate(StrictModel):
    text: str = Field(min_length=5, max_length=4000)
    type: RequirementType
    applicability: RequirementApplicability = (
        RequirementApplicability.STATICALLY_VERIFIABLE
    )
    source_references: list[str] = Field(min_length=1)
    predicates: list[dict[str, Any]] = Field(min_length=1)


class RequirementCandidateSet(StrictModel):
    requirements: list[RequirementCandidate] = Field(min_length=1, max_length=100)
