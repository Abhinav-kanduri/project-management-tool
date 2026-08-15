from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID, uuid4

from psycopg.errors import UndefinedTable
from psycopg.types.json import Jsonb

from app.database import get_connection


class SnapshotRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def find_completed(
        self,
        *,
        project_repository_id: UUID,
        commit_sha: str,
        scanner_version: str,
    ) -> dict[str, Any] | None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select * from repository_snapshots
                where project_repository_id=%s and commit_sha=%s
                  and scanner_version=%s and status='COMPLETED'
                """,
                (project_repository_id, commit_sha, scanner_version),
            )
            return cursor.fetchone()

    def latest_by_commit(self, project_repository_id: UUID) -> dict[str, dict[str, Any]]:
        try:
            with self._connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    select distinct on (commit_sha) * from repository_snapshots
                    where project_repository_id=%s and status='COMPLETED'
                    order by commit_sha, completed_at desc nulls last, updated_at desc
                    """,
                    (project_repository_id,),
                )
                return {str(row["commit_sha"]): row for row in cursor.fetchall()}
        except UndefinedTable:
            # Branch discovery can still work before Impact Analysis migrations
            # are deployed; synchronization will report the missing schema.
            return {}

    def create(
        self,
        *,
        project_repository_id: UUID,
        repository_id: UUID,
        product_space_id: UUID,
        project_id: UUID,
        branch: str,
        commit_sha: str,
        scanner_version: str,
    ) -> UUID:
        snapshot_id = uuid4()
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into repository_snapshots(
                    id, project_repository_id, repository_id, product_space_id,
                    project_id, branch, commit_sha, status, scanner_version,
                    started_at
                ) values (%s,%s,%s,%s,%s,%s,%s,'DOWNLOADING',%s,now())
                on conflict (project_repository_id, commit_sha, scanner_version)
                do update set status='DOWNLOADING', error_code=null,
                              error_message=null, started_at=now(), updated_at=now()
                returning id
                """,
                (
                    snapshot_id,
                    project_repository_id,
                    repository_id,
                    product_space_id,
                    project_id,
                    branch,
                    commit_sha,
                    scanner_version,
                ),
            )
            result = cursor.fetchone()["id"]
            connection.commit()
            return result

    def set_status(
        self,
        snapshot_id: UUID,
        status: str,
        *,
        manifest: list[dict[str, Any]] | None = None,
        discovered_files: int | None = None,
        indexed_files: int | None = None,
        skipped_files: int | None = None,
        coverage_percent: float | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update repository_snapshots
                set status=%s,
                    manifest=coalesce(%s,manifest),
                    discovered_files=coalesce(%s,discovered_files),
                    indexed_files=coalesce(%s,indexed_files),
                    skipped_files=coalesce(%s,skipped_files),
                    coverage_percent=coalesce(%s,coverage_percent),
                    error_code=%s, error_message=%s,
                    completed_at=case when %s in ('COMPLETED','FAILED') then now() else completed_at end,
                    updated_at=now()
                where id=%s
                returning *
                """,
                (
                    status,
                    Jsonb(manifest) if manifest is not None else None,
                    discovered_files,
                    indexed_files,
                    skipped_files,
                    coverage_percent,
                    error_code,
                    error_message,
                    status,
                    snapshot_id,
                ),
            )
            row = cursor.fetchone()
            connection.commit()
            return row
