from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from psycopg import Error as PsycopgError

from app.database import get_connection
from app.github_summary.github_client import GitHubClient
from app.github_summary.github_url import parse_github_repository_url
from app.github_summary.settings import GitHubSummarySettings
from app.impact_analysis.domain import RepositoryMappingRecord
from app.impact_analysis.repositories.snapshots import SnapshotRepository
from app.impact_analysis.services.snapshot_service import SnapshotService


class RepositoryLinkHasDependencies(RuntimeError):
    def __init__(self, dependencies: dict[str, int]) -> None:
        super().__init__("Repository link has persisted analysis dependencies.")
        self.dependencies = dependencies


class RepositoryBranchService:
    def __init__(
        self,
        settings: GitHubSummarySettings | None = None,
        snapshot_repository: SnapshotRepository | None = None,
        snapshot_service: SnapshotService | None = None,
    ) -> None:
        self.settings = settings or GitHubSummarySettings()
        self.snapshot_repository = snapshot_repository or SnapshotRepository()
        self.snapshot_service = snapshot_service or SnapshotService(settings=self.settings)

    def _linked_repository(self, *, project_repository_id: UUID, actor: UUID) -> dict:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select link.id project_repository_id, link.product_space_id,
                       link.project_id, r.id repository_id,
                       r.github_repository_id, r.full_name, r.html_url,
                       r.default_branch, r.private, r.archived
                from project_github_repositories link
                join github_repositories r on r.id=link.repository_id
                where link.id=%s and r.archived=false
                """,
                (project_repository_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise LookupError("Linked repository was not found.")
            cursor.execute(
                "select 1 from project_members where project_id=%s and user_id=%s",
                (row["project_id"], actor),
            )
            if not cursor.fetchone():
                raise PermissionError("Actor is not a member of the Project.")
        return row

    async def list(self, *, project_repository_id: UUID, actor: UUID) -> dict:
        row = self._linked_repository(
            project_repository_id=project_repository_id, actor=actor
        )
        reference = parse_github_repository_url(
            row["html_url"], allowed_hosts=self.settings.allowed_hosts
        )
        async with GitHubClient(self.settings) as github:
            payload = await github.list_branches(reference)
        snapshots = self.snapshot_repository.latest_by_commit(project_repository_id)
        branches = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            commit_sha = str((item.get("commit") or {}).get("sha") or "") or None
            snapshot = snapshots.get(commit_sha or "")
            branches.append(
                {
                    "name": str(item["name"]),
                    "commit_sha": commit_sha,
                    "protected": bool(item.get("protected", False)),
                    "snapshot_id": snapshot.get("id") if snapshot else None,
                    "sync_status": snapshot.get("status") if snapshot else None,
                    "last_synced_at": snapshot.get("completed_at") if snapshot else None,
                }
            )
        return {"branches": branches, "refreshed_at": datetime.now(UTC)}

    async def sync(
        self,
        *,
        project_repository_id: UUID,
        actor: UUID,
        branch: str,
        force_refresh: bool,
    ) -> dict:
        row = self._linked_repository(
            project_repository_id=project_repository_id, actor=actor
        )
        mapping = RepositoryMappingRecord(
            project_repository_id=row["project_repository_id"],
            repository_id=row["repository_id"],
            github_repository_id=row["github_repository_id"],
            full_name=row["full_name"],
            repository_url=row["html_url"],
            default_branch=row["default_branch"],
            private=row["private"],
            archived=row["archived"],
        )
        try:
            snapshot = await self.snapshot_service.create_for_repository(
                repository=mapping,
                product_space_id=row["product_space_id"],
                project_id=row["project_id"],
                requested_ref=branch,
                force_refresh=force_refresh,
            )
        except PsycopgError as error:
            raise RuntimeError(
                "Repository source-index storage is unavailable. Apply PostgreSQL "
                "Impact Analysis migrations 25 through 29."
            ) from error
        synced_at = snapshot.get("completed_at") or snapshot.get("updated_at")
        return {
            "snapshot_id": snapshot["id"],
            "branch": branch,
            "commit_sha": snapshot["commit_sha"],
            "status": snapshot["status"],
            "cache_hit": bool(snapshot.get("cache_hit", False)),
            "synced_at": synced_at or datetime.now(UTC),
            "discovered_files": int(snapshot.get("discovered_files") or 0),
            "indexed_files": int(snapshot.get("indexed_files") or 0),
            "skipped_files": int(snapshot.get("skipped_files") or 0),
            "coverage_percent": float(snapshot.get("coverage_percent") or 0),
        }

    def unlink(self, *, project_repository_id: UUID, actor: UUID) -> dict:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select link.id project_repository_id, link.project_id,
                       r.full_name repository_full_name
                from project_github_repositories link
                join github_repositories r on r.id=link.repository_id
                where link.id=%s
                for update
                """,
                (project_repository_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise LookupError("Linked repository was not found.")
            cursor.execute(
                """
                select role from project_members
                where project_id=%s and user_id=%s
                  and role in ('PROJECT_ADMIN','PRODUCT_OWNER','ADMIN')
                """,
                (row["project_id"], actor),
            )
            if not cursor.fetchone():
                raise PermissionError(
                    "Project Admin or Product Owner permission is required to unlink a repository."
                )
            dependencies: dict[str, int] = {}
            for table in ("repository_snapshots", "impact_analysis_runs"):
                cursor.execute(
                    "select to_regclass(%s) is not null present",
                    (f"public.{table}",),
                )
                if not cursor.fetchone()["present"]:
                    continue
                cursor.execute(
                    f"select count(*)::integer total from {table} where project_repository_id=%s",
                    (project_repository_id,),
                )
                total = int(cursor.fetchone()["total"])
                if total:
                    dependencies[table] = total
            if dependencies:
                raise RepositoryLinkHasDependencies(dependencies)
            cursor.execute(
                "delete from project_github_repositories where id=%s",
                (project_repository_id,),
            )
            connection.commit()
        return {
            "unlinked": True,
            "project_repository_id": project_repository_id,
            "project_id": row["project_id"],
            "repository_full_name": row["repository_full_name"],
        }
