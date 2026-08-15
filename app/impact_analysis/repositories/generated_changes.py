from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.database import get_connection
from app.impact_analysis.remediation.models import (
    ChangeProposal,
    PullRequestResult,
    ValidationCheck,
)


class ChangeNotFoundError(LookupError):
    pass


class ChangeStateError(ValueError):
    pass


class GeneratedChangeRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def request(self, *, finding_id: UUID, actor: UUID) -> dict[str, Any]:
        change_id = uuid4()
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select f.id,f.status,f.code_generation_available,r.applicability,
                       ar.status run_status,
                       ar.snapshot_id,rs.commit_sha,ar.project_id
                from impact_findings f join impact_requirements r on r.id=f.requirement_id
                join impact_analysis_runs ar on ar.id=f.run_id
                join repository_snapshots rs on rs.id=ar.snapshot_id
                where f.id=%s
                """,
                (finding_id,),
            )
            finding = cursor.fetchone()
            if not finding:
                raise ChangeNotFoundError(str(finding_id))
            self._authorize(cursor, actor, finding["project_id"])
            if finding["run_status"] != "COMPLETED":
                raise ChangeStateError("The analysis run must be completed.")
            if finding["status"] not in {"PARTIAL", "MISSING"}:
                raise ChangeStateError("Only PARTIAL or MISSING findings are eligible.")
            if not finding["code_generation_available"]:
                raise ChangeStateError("Code generation is not available for this finding.")
            if finding["applicability"] != "STATICALLY_VERIFIABLE":
                raise ChangeStateError("This finding requires non-static evidence.")
            cursor.execute(
                """
                select * from generated_changes
                where finding_id=%s and snapshot_id=%s
                  and status not in ('FAILED','REJECTED','MERGED')
                order by created_at desc limit 1
                """,
                (finding_id, finding["snapshot_id"]),
            )
            existing = cursor.fetchone()
            if existing:
                return existing
            cursor.execute(
                """
                insert into generated_changes(
                    id,finding_id,snapshot_id,status,prompt_version,
                    base_commit_sha,requested_by,metadata
                ) values (%s,%s,%s,'REQUESTED','code-generation-v1',%s,%s,%s)
                returning *
                """,
                (
                    change_id,finding_id,finding["snapshot_id"],finding["commit_sha"],
                    str(actor),Jsonb({"approval_required": True}),
                ),
            )
            row = cursor.fetchone()
            connection.commit()
            return row

    def get(self, change_id: UUID, *, actor: UUID) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select c.*,ar.project_id from generated_changes c
                join impact_findings f on f.id=c.finding_id
                join impact_analysis_runs ar on ar.id=f.run_id where c.id=%s
                """,
                (change_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ChangeNotFoundError(str(change_id))
            self._authorize(cursor, actor, row["project_id"])
            cursor.execute(
                "select * from generated_change_validations where generated_change_id=%s order by created_at,id",
                (change_id,),
            )
            row["validations"] = cursor.fetchall()
            return row

    def context(self, change_id: UUID, *, actor: UUID) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select c.*,f.status finding_status,f.what_present,f.what_missing,
                       f.technical_reason,f.explanation,f.recommendation,
                       r.id requirement_id,r.requirement_text,r.requirement_type,
                       r.expected_predicates,r.applicability,ar.project_id,
                       gr.full_name repository_name,rs.branch,rs.commit_sha
                from generated_changes c
                join impact_findings f on f.id=c.finding_id
                join impact_requirements r on r.id=f.requirement_id
                join impact_analysis_runs ar on ar.id=f.run_id
                join repository_snapshots rs on rs.id=c.snapshot_id
                join project_github_repositories pgr on pgr.id=ar.project_repository_id
                join github_repositories gr on gr.id=pgr.repository_id
                where c.id=%s
                """,
                (change_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ChangeNotFoundError(str(change_id))
            self._authorize(cursor, actor, row["project_id"])
            cursor.execute(
                """
                select evidence_type,direction,file_path,symbol,start_line,end_line,
                       description,excerpt,content_sha256 from impact_evidence
                where requirement_id=%s order by rank nulls last,id limit 20
                """,
                (row["requirement_id"],),
            )
            row["evidence"] = cursor.fetchall()
            return row

    def save_proposal(
        self, change_id: UUID, *, proposal: ChangeProposal, actor: UUID
    ) -> dict[str, Any]:
        self.get(change_id, actor=actor)
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update generated_changes set status='GENERATED',proposed_files=%s,
                    patch=%s,explanation=%s,tests_proposed=%s,updated_at=now()
                where id=%s and status in ('REQUESTED','GENERATING','FAILED') returning *
                """,
                (
                    Jsonb([item.model_dump(mode="json") for item in proposal.proposed_files]),
                    proposal.patch,proposal.explanation,Jsonb(proposal.tests_proposed),change_id,
                ),
            )
            row = cursor.fetchone()
            if not row:
                raise ChangeStateError("Change is not in a generatable state.")
            connection.commit()
            return row

    def save_validations(
        self, change_id: UUID, *, checks: list[ValidationCheck], actor: UUID
    ) -> dict[str, Any]:
        change = self.get(change_id, actor=actor)
        if change["status"] not in {"GENERATED", "VALIDATION_FAILED", "VALIDATED"}:
            raise ChangeStateError("A generated patch is required before validation.")
        required = {
            "PATH_SAFETY",
            "FORMAT",
            "POLICY",
            "LINT",
            "COMPILE",
            "UNIT_TEST",
            "SECURITY",
        }
        statuses = {item.check_type: item.status for item in checks}
        passed = all(statuses.get(check_type) == "PASSED" for check_type in required)
        status = "VALIDATED" if passed else "VALIDATION_FAILED"
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "delete from generated_change_validations where generated_change_id=%s",
                (change_id,),
            )
            for item in checks:
                cursor.execute(
                    """
                    insert into generated_change_validations(
                        generated_change_id,check_type,command,status,exit_code,
                        log_excerpt,started_at,completed_at
                    ) values (%s,%s,%s,%s,%s,%s,now(),now())
                    """,
                    (
                        change_id,item.check_type,item.command,item.status,
                        item.exit_code,item.log_excerpt,
                    ),
                )
            cursor.execute(
                """
                update generated_changes set status=%s,validation_summary=%s,
                    updated_at=now() where id=%s returning *
                """,
                (
                    status,
                    Jsonb({"passed": passed,"checks": [item.model_dump() for item in checks]}),
                    change_id,
                ),
            )
            row = cursor.fetchone()
            connection.commit()
            return row

    def decide(
        self,
        change_id: UUID,
        *,
        actor: UUID,
        approved: bool,
        comment: str | None,
    ) -> dict[str, Any]:
        change = self.get(change_id, actor=actor)
        if approved and change["status"] != "VALIDATED":
            raise ChangeStateError("Only a validated change can be approved.")
        if not approved and change["status"] in {"PR_CREATED", "MERGED"}:
            raise ChangeStateError("A published change cannot be rejected here.")
        target = "APPROVED" if approved else "REJECTED"
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update generated_changes set status=%s,approved_by=%s,
                    approval_comment=%s,approved_at=now(),updated_at=now()
                where id=%s returning *
                """,
                (target, str(actor), comment, change_id),
            )
            row = cursor.fetchone()
            connection.commit()
            return row

    def record_pull_request(
        self,
        change_id: UUID,
        *,
        result: PullRequestResult,
        actor: UUID,
    ) -> dict[str, Any]:
        change = self.get(change_id, actor=actor)
        if change["status"] != "APPROVED":
            raise ChangeStateError("Human approval is required before publishing.")
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update generated_changes set status='PR_CREATED',branch_name=%s,
                    commit_sha=%s,pull_request_number=%s,pull_request_url=%s,
                    updated_at=now() where id=%s returning *
                """,
                (
                    result.branch_name,result.commit_sha,result.pull_request_number,
                    result.pull_request_url,change_id,
                ),
            )
            row = cursor.fetchone()
            connection.commit()
            return row

    @staticmethod
    def _authorize(cursor, actor: UUID, project_id: UUID) -> None:
        cursor.execute(
            "select 1 from project_members where project_id=%s and user_id=%s",
            (project_id, actor),
        )
        if not cursor.fetchone():
            raise PermissionError("Actor is not a member of the Project.")
