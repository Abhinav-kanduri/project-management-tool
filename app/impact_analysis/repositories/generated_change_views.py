from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from app.database import get_connection
from app.impact_analysis.repositories.generated_changes import ChangeNotFoundError


class GeneratedChangeViewRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def get(self, change_id: UUID, *, actor: UUID) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select c.*,ar.project_id,gr.full_name repository_name,rs.branch base_ref
                from generated_changes c
                join impact_findings f on f.id=c.finding_id
                join impact_analysis_runs ar on ar.id=f.run_id
                join repository_snapshots rs on rs.id=c.snapshot_id
                join project_github_repositories pgr on pgr.id=ar.project_repository_id
                join github_repositories gr on gr.id=pgr.repository_id where c.id=%s
                """,
                (change_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ChangeNotFoundError(str(change_id))
            cursor.execute(
                "select 1 from project_members where project_id=%s and user_id=%s",
                (row["project_id"], actor),
            )
            if not cursor.fetchone():
                raise PermissionError("Actor is not a member of the Project.")
            cursor.execute(
                "select * from generated_change_validations where generated_change_id=%s order by created_at,id",
                (change_id,),
            )
            row["validations"] = cursor.fetchall()
            return row
