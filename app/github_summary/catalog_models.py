from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GitHubRepositoryOption(BaseModel):
    id: int = Field(gt=0, description="Stable numeric GitHub repository ID")
    node_id: str | None = None
    owner: str
    name: str
    full_name: str
    repository_url: str
    description: str | None = None
    default_branch: str
    visibility: str
    private: bool
    archived: bool
    fork: bool
    pushed_at: datetime | None = None
    updated_at: datetime | None = None
    imported: bool = False
    catalog_repository_id: UUID | None = None
    association_id: UUID | None = None


class GitHubRepositoryListResponse(BaseModel):
    page: int
    per_page: int
    returned: int
    has_next_page: bool
    repositories: list[GitHubRepositoryOption]


class GitHubRepositoryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github_repository_id: int = Field(gt=0)
    product_space_id: UUID
    project_id: UUID


class ImportedGitHubRepository(BaseModel):
    association_id: UUID
    catalog_repository_id: UUID
    github_repository_id: int
    product_space_id: UUID
    product_space_name: str
    project_id: UUID
    project_name: str
    owner: str
    name: str
    full_name: str
    repository_url: str
    description: str | None = None
    default_branch: str
    visibility: str
    private: bool
    archived: bool
    linked_at: datetime
    synced_at: datetime


class ImportedGitHubRepositoryListResponse(BaseModel):
    repositories: list[ImportedGitHubRepository]
