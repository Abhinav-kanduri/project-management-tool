from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any
from uuid import UUID

from psycopg import Error as PsycopgError
from psycopg.types.json import Jsonb

from app.database import get_connection
from app.github_summary.catalog_models import (
    GitHubRepositoryListResponse,
    GitHubRepositoryOption,
    ImportedGitHubRepository,
    ImportedGitHubRepositoryListResponse,
)
from app.github_summary.errors import SummaryDatabaseError
from app.github_summary.github_client import GitHubClient, GitHubRepositoryRecord
from app.github_summary.settings import GitHubSummarySettings


class RepositoryScopeError(RuntimeError):
    pass


class GitHubConfigurationError(RuntimeError):
    pass


class GitHubRepositoryCatalog:
    def linked_by_github_id(self, project_id: UUID) -> dict[int, dict[str, Any]]:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    select r.github_repository_id, r.id catalog_repository_id,
                           link.id association_id
                    from project_github_repositories link
                    join github_repositories r on r.id = link.repository_id
                    where link.project_id = %s
                    """,
                    (project_id,),
                )
                return {int(row["github_repository_id"]): row for row in cursor.fetchall()}
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to load linked GitHub repositories") from exc

    def import_repository(
        self,
        repository: GitHubRepositoryRecord,
        *,
        product_space_id: UUID,
        project_id: UUID,
    ) -> dict[str, Any]:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    select p.id project_id, p.name project_name,
                           ps.id product_space_id, ps.name product_space_name
                    from projects p
                    join product_spaces ps on ps.id = p.product_space_id
                    where p.id = %s
                      and p.product_space_id = %s
                      and p.archived_at is null
                      and ps.archived_at is null
                    for update
                    """,
                    (project_id, product_space_id),
                )
                scope = cursor.fetchone()
                if not scope:
                    raise RepositoryScopeError(
                        "Project does not belong to the selected Product Space."
                    )
                cursor.execute(
                    """
                    insert into github_repositories (
                        github_repository_id, node_id, owner_login, name, full_name,
                        html_url, description, default_branch, visibility, private,
                        archived, is_fork, pushed_at, github_updated_at, metadata, synced_at
                    ) values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, now()
                    )
                    on conflict (github_repository_id) do update set
                        node_id = excluded.node_id,
                        owner_login = excluded.owner_login,
                        name = excluded.name,
                        full_name = excluded.full_name,
                        html_url = excluded.html_url,
                        description = excluded.description,
                        default_branch = excluded.default_branch,
                        visibility = excluded.visibility,
                        private = excluded.private,
                        archived = excluded.archived,
                        is_fork = excluded.is_fork,
                        pushed_at = excluded.pushed_at,
                        github_updated_at = excluded.github_updated_at,
                        metadata = excluded.metadata,
                        synced_at = now(),
                        updated_at = now()
                    returning id, synced_at
                    """,
                    (
                        repository.id,
                        repository.node_id,
                        repository.owner,
                        repository.name,
                        repository.full_name,
                        repository.repository_url,
                        repository.description,
                        repository.default_branch,
                        repository.visibility,
                        repository.private,
                        repository.archived,
                        repository.fork,
                        repository.pushed_at,
                        repository.updated_at,
                        Jsonb(
                            {
                                **asdict(repository),
                                "pushed_at": repository.pushed_at.isoformat()
                                if repository.pushed_at
                                else None,
                                "updated_at": repository.updated_at.isoformat()
                                if repository.updated_at
                                else None,
                            }
                        ),
                    ),
                )
                catalog_row = cursor.fetchone()
                catalog_repository_id = catalog_row["id"]
                cursor.execute(
                    """
                    insert into project_github_repositories (
                        product_space_id, project_id, repository_id
                    ) values (%s, %s, %s)
                    on conflict (project_id, repository_id) do update set
                        product_space_id = excluded.product_space_id,
                        updated_at = now()
                    returning id, linked_at
                    """,
                    (product_space_id, project_id, catalog_repository_id),
                )
                association = cursor.fetchone()
                connection.commit()
                return {
                    "association_id": association["id"],
                    "catalog_repository_id": catalog_repository_id,
                    "github_repository_id": repository.id,
                    "product_space_id": scope["product_space_id"],
                    "product_space_name": scope["product_space_name"],
                    "project_id": scope["project_id"],
                    "project_name": scope["project_name"],
                    "owner": repository.owner,
                    "name": repository.name,
                    "full_name": repository.full_name,
                    "repository_url": repository.repository_url,
                    "description": repository.description,
                    "default_branch": repository.default_branch,
                    "visibility": repository.visibility,
                    "private": repository.private,
                    "archived": repository.archived,
                    "linked_at": association["linked_at"],
                    "synced_at": catalog_row["synced_at"],
                }
        except RepositoryScopeError:
            raise
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to save the GitHub repository link") from exc

    def list_imported(
        self,
        *,
        product_space_id: UUID | None,
        project_id: UUID | None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        parameters: list[Any] = []
        if product_space_id:
            filters.append("link.product_space_id = %s")
            parameters.append(product_space_id)
        if project_id:
            filters.append("link.project_id = %s")
            parameters.append(project_id)
        where = f"where {' and '.join(filters)}" if filters else ""
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select link.id association_id, r.id catalog_repository_id,
                           r.github_repository_id, link.product_space_id,
                           ps.name product_space_name, link.project_id,
                           p.name project_name, r.owner_login owner, r.name,
                           r.full_name, r.html_url repository_url, r.description,
                           r.default_branch, r.visibility, r.private, r.archived,
                           link.linked_at, r.synced_at
                    from project_github_repositories link
                    join github_repositories r on r.id = link.repository_id
                    join product_spaces ps on ps.id = link.product_space_id
                    join projects p on p.id = link.project_id
                    {where}
                    order by r.full_name
                    """,
                    tuple(parameters),
                )
                return cursor.fetchall()
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to list imported GitHub repositories") from exc


class GitHubRepositoryCatalogService:
    def __init__(self, settings: GitHubSummarySettings | None = None) -> None:
        self.settings = settings or GitHubSummarySettings()
        self.catalog = GitHubRepositoryCatalog()

    def _require_token(self) -> None:
        if not self.settings.github_token:
            raise GitHubConfigurationError(
                "GITHUB_TOKEN is required to list repositories available to the current account."
            )

    async def list_repositories(
        self,
        *,
        page: int,
        per_page: int,
        project_id: UUID | None,
    ) -> GitHubRepositoryListResponse:
        self._require_token()
        async with GitHubClient(self.settings) as github:
            repositories = await github.list_repositories(page=page, per_page=per_page)
        linked = (
            await asyncio.to_thread(self.catalog.linked_by_github_id, project_id)
            if project_id
            else {}
        )
        options = []
        for repository in repositories:
            association = linked.get(repository.id)
            options.append(
                GitHubRepositoryOption(
                    **asdict(repository),
                    imported=association is not None,
                    catalog_repository_id=(
                        association["catalog_repository_id"] if association else None
                    ),
                    association_id=association["association_id"] if association else None,
                )
            )
        return GitHubRepositoryListResponse(
            page=page,
            per_page=per_page,
            returned=len(options),
            has_next_page=len(options) == per_page,
            repositories=options,
        )

    async def import_repository(
        self,
        *,
        github_repository_id: int,
        product_space_id: UUID,
        project_id: UUID,
    ) -> ImportedGitHubRepository:
        self._require_token()
        async with GitHubClient(self.settings) as github:
            repository = await github.get_repository_by_id(github_repository_id)
        row = await asyncio.to_thread(
            self.catalog.import_repository,
            repository,
            product_space_id=product_space_id,
            project_id=project_id,
        )
        return ImportedGitHubRepository.model_validate(row)

    async def list_imported(
        self,
        *,
        product_space_id: UUID | None,
        project_id: UUID | None,
    ) -> ImportedGitHubRepositoryListResponse:
        rows = await asyncio.to_thread(
            self.catalog.list_imported,
            product_space_id=product_space_id,
            project_id=project_id,
        )
        return ImportedGitHubRepositoryListResponse(
            repositories=[ImportedGitHubRepository.model_validate(row) for row in rows]
        )
