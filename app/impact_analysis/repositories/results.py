from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from app.database import get_connection
from app.impact_analysis.enums import FindingStatus
from app.impact_analysis.repositories.analysis import AnalysisRunNotFoundError


class AnalysisResultRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def complete(
        self,
        *,
        run_id: UUID,
        score: float | None,
        applicable_weight: float,
        excluded_weight: float,
        counts: dict[FindingStatus, int],
    ) -> None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update impact_analysis_runs set status='COMPLETED',stage='COMPLETED',
                    progress_percent=100,message='Analysis completed',score=%s,
                    applicable_weight=%s,excluded_weight=%s,present_count=%s,
                    partial_count=%s,missing_count=%s,unknown_count=%s,
                    completed_at=now(),updated_at=now() where id=%s
                returning organization_id,product_space_id,project_id,scope_type,scope_id
                """,
                (
                    score,applicable_weight,excluded_weight,
                    counts.get(FindingStatus.PRESENT, 0),
                    counts.get(FindingStatus.PARTIAL, 0),
                    counts.get(FindingStatus.MISSING, 0),
                    counts.get(FindingStatus.UNKNOWN, 0),run_id,
                ),
            )
            scope = cursor.fetchone()
            if not scope:
                raise AnalysisRunNotFoundError(str(run_id))
            cursor.execute(
                """
                insert into analysis_score_history(
                    organization_id,product_space_id,project_id,scope_type,scope_id,
                    run_id,score,applicable_weight,excluded_weight,present_count,
                    partial_count,missing_count,unknown_count,calculation_version
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'completion-v1')
                on conflict (run_id) do update set score=excluded.score,
                    applicable_weight=excluded.applicable_weight,
                    excluded_weight=excluded.excluded_weight,
                    present_count=excluded.present_count,partial_count=excluded.partial_count,
                    missing_count=excluded.missing_count,unknown_count=excluded.unknown_count
                """,
                (
                    scope["organization_id"],scope["product_space_id"],scope["project_id"],
                    scope["scope_type"],scope["scope_id"],run_id,score,applicable_weight,
                    excluded_weight,counts.get(FindingStatus.PRESENT, 0),
                    counts.get(FindingStatus.PARTIAL, 0),counts.get(FindingStatus.MISSING, 0),
                    counts.get(FindingStatus.UNKNOWN, 0),
                ),
            )
            connection.commit()

    def get_run(self, run_id: UUID, *, actor: str) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select r.*,f.feature_key,f.title feature_title,
                       us.story_key,us.title story_title,
                       gr.full_name repository_name,rs.branch,rs.commit_sha
                from impact_analysis_runs r
                left join features f on r.scope_type='FEATURE' and f.id=r.scope_id
                left join user_stories us on r.scope_type='USER_STORY' and us.id=r.scope_id
                join project_github_repositories pgr on pgr.id=r.project_repository_id
                join github_repositories gr on gr.id=pgr.repository_id
                left join repository_snapshots rs on rs.id=r.snapshot_id
                where r.id=%s
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise AnalysisRunNotFoundError(str(run_id))
            self._authorize(cursor, actor, row["project_id"])
            return row

    def list_requirements(self, run_id: UUID, *, actor: str) -> list[dict[str, Any]]:
        self.get_run(run_id, actor=actor)
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "select * from impact_requirements where run_id=%s order by requirement_key",
                (run_id,),
            )
            return cursor.fetchall()

    def list_findings(self, run_id: UUID, *, actor: str) -> list[dict[str, Any]]:
        self.get_run(run_id, actor=actor)
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select f.*,r.requirement_key,r.requirement_text,r.requirement_type,
                       r.applicability,r.weight,
                       (select count(*) from impact_evidence e where e.requirement_id=r.id) evidence_count
                from impact_findings f join impact_requirements r on r.id=f.requirement_id
                where f.run_id=%s order by r.requirement_key
                """,
                (run_id,),
            )
            return cursor.fetchall()

    def get_finding(self, finding_id: UUID, *, actor: str) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select f.*,r.requirement_key,r.requirement_text,r.requirement_type,
                       r.applicability,r.weight,ar.project_id
                from impact_findings f join impact_requirements r on r.id=f.requirement_id
                join impact_analysis_runs ar on ar.id=f.run_id where f.id=%s
                """,
                (finding_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise AnalysisRunNotFoundError(str(finding_id))
            self._authorize(cursor, actor, row["project_id"])
            cursor.execute(
                "select * from impact_evidence where requirement_id=%s order by rank nulls last,id",
                (row["requirement_id"],),
            )
            row["evidence"] = cursor.fetchall()
            return row

    def history(
        self, *, project_id: UUID, scope_type: str, scope_id: UUID, actor: str
    ) -> list[dict[str, Any]]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            self._authorize(cursor, actor, project_id)
            cursor.execute(
                """
                select h.* from analysis_score_history h
                where h.project_id=%s and h.scope_type=%s and h.scope_id=%s
                order by h.created_at desc limit 100
                """,
                (project_id, scope_type, scope_id),
            )
            return cursor.fetchall()

    @staticmethod
    def _authorize(cursor, actor: str, project_id: UUID) -> None:
        try:
            actor_id = UUID(actor)
        except ValueError:
            return
        cursor.execute(
            "select 1 from project_members where project_id=%s and user_id=%s",
            (project_id, actor_id),
        )
        if not cursor.fetchone():
            raise PermissionError("Actor is not a member of the Project.")
