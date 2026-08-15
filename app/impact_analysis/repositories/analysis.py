from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.database import get_connection
from app.impact_analysis.domain import RequirementPackage
from app.impact_analysis.enums import AnalysisStage, FindingStatus, RunStatus
from app.impact_analysis.schemas import (
    AtomicRequirement,
    EvidenceRecord,
    LLMComparisonCandidate,
    StartAnalysisRequest,
)


class AnalysisRunNotFoundError(LookupError):
    pass


class AnalysisRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def create_or_get(
        self,
        *,
        package: RequirementPackage,
        request: StartAnalysisRequest,
        actor: str,
    ) -> tuple[dict[str, Any], bool]:
        run_id = uuid4()
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                insert into impact_analysis_runs(
                    id,organization_id,product_space_id,project_id,release_id,
                    scope_type,scope_id,project_repository_id,requested_ref,
                    client_request_id,started_by
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (project_id,client_request_id) do nothing
                returning *
                """,
                (
                    run_id,
                    package.project.organization_id,
                    request.product_space_id,
                    request.project_id,
                    request.release_id,
                    request.scope_type.value,
                    request.scope_id,
                    request.project_repository_id,
                    request.ref,
                    request.client_request_id,
                    actor,
                ),
            )
            row = cursor.fetchone()
            created = row is not None
            if row is None:
                cursor.execute(
                    "select * from impact_analysis_runs where project_id=%s and client_request_id=%s",
                    (request.project_id, request.client_request_id),
                )
                row = cursor.fetchone()
            connection.commit()
        return row, created

    def update_stage(
        self,
        run_id: UUID,
        *,
        status: RunStatus = RunStatus.RUNNING,
        stage: AnalysisStage,
        progress: int,
        message: str | None = None,
        snapshot_id: UUID | None = None,
    ) -> None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update impact_analysis_runs
                set status=%s,stage=%s,progress_percent=%s,message=%s,
                    snapshot_id=coalesce(%s,snapshot_id),
                    started_at=coalesce(started_at,now()),updated_at=now()
                where id=%s
                """,
                (status.value, stage.value, progress, message, snapshot_id, run_id),
            )
            connection.commit()

    def fail(self, run_id: UUID, *, code: str, message: str) -> None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update impact_analysis_runs set status='FAILED',
                    message=case
                        when stage='FAILED' then 'Analysis failed'
                        else 'Analysis failed during '
                             || replace(initcap(stage), '_', ' ')
                    end,
                    error_code=%s,error_message=%s,
                    completed_at=now(),updated_at=now() where id=%s
                """,
                (code, message[:2000], run_id),
            )
            connection.commit()

    def replace_requirements(
        self, run_id: UUID, requirements: list[AtomicRequirement]
    ) -> list[AtomicRequirement]:
        persisted = []
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("delete from impact_requirements where run_id=%s", (run_id,))
            for requirement in requirements:
                first = requirement.provenance[0]
                cursor.execute(
                    """
                    insert into impact_requirements(
                        run_id,requirement_key,requirement_text,requirement_type,
                        applicability,source_type,source_id,source_locator,
                        provenance,weight,expected_predicates,decomposition_metadata
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    returning id
                    """,
                    (
                        run_id,
                        requirement.requirement_key,
                        requirement.text,
                        requirement.type.value,
                        requirement.applicability.value,
                        first.source_type,
                        first.source_id,
                        Jsonb(first.source_locator),
                        Jsonb([item.model_dump(mode="json") for item in requirement.provenance]),
                        requirement.weight,
                        Jsonb([item.model_dump(mode="json") for item in requirement.expected_predicates]),
                        Jsonb({"version": "requirements-v1"}),
                    ),
                )
                persisted.append(
                    requirement.model_copy(update={"requirement_id": cursor.fetchone()["id"]})
                )
            cursor.execute(
                "update impact_analysis_runs set total_requirements=%s,updated_at=now() where id=%s",
                (len(persisted), run_id),
            )
            connection.commit()
        return persisted

    def replace_result(
        self,
        *,
        run_id: UUID,
        snapshot_id: UUID,
        requirement: AtomicRequirement,
        evidence: list[EvidenceRecord],
        finding: LLMComparisonCandidate,
        predicate_results: list[dict],
        completion: float | None,
        contribution: float | None,
    ) -> UUID:
        if requirement.requirement_id is None:
            raise ValueError("Persisted requirement ID is required")
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "delete from impact_evidence where run_id=%s and requirement_id=%s",
                (run_id, requirement.requirement_id),
            )
            for item in evidence:
                metadata = item.metadata
                cursor.execute(
                    """
                    insert into impact_evidence(
                        id,run_id,requirement_id,snapshot_id,evidence_type,direction,
                        retrieval_method,source_ref,file_id,symbol_id,chunk_id,
                        file_path,symbol,start_line,end_line,description,excerpt,
                        content_sha256,rank,score,metadata,evidence_key
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        item.evidence_id,run_id,item.requirement_id,snapshot_id,
                        item.type.value,item.direction.value,item.retrieval_method.value,
                        item.repository,metadata.get("file_id"),metadata.get("symbol_id"),
                        metadata.get("chunk_id"),item.file_path,item.symbol,item.start_line,
                        item.end_line,item.description,item.excerpt,
                        metadata.get("content_sha256"),item.rank,item.score,Jsonb(metadata),
                        metadata.get("candidate_key", str(item.evidence_id)),
                    ),
                )
            cursor.execute(
                """
                insert into impact_findings(
                    run_id,requirement_id,status,what_present,what_missing,
                    reason_code,technical_reason,explanation,impacts,recommendation,
                    confidence,completion,score_contribution,code_generation_available,
                    predicate_results,prompt_version,metadata
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (run_id,requirement_id) do update set
                    status=excluded.status,what_present=excluded.what_present,
                    what_missing=excluded.what_missing,reason_code=excluded.reason_code,
                    technical_reason=excluded.technical_reason,explanation=excluded.explanation,
                    impacts=excluded.impacts,recommendation=excluded.recommendation,
                    confidence=excluded.confidence,completion=excluded.completion,
                    score_contribution=excluded.score_contribution,
                    code_generation_available=excluded.code_generation_available,
                    predicate_results=excluded.predicate_results,updated_at=now()
                returning id
                """,
                (
                    run_id,requirement.requirement_id,finding.candidate_status.value,
                    finding.present_summary,finding.missing_summary,finding.reason_code.value,
                    finding.technical_reason,finding.explanation,
                    Jsonb([item.model_dump(mode="json") for item in finding.impacts]),
                    finding.recommendation,finding.confidence,completion,contribution,
                    finding.candidate_status in {FindingStatus.PARTIAL, FindingStatus.MISSING},
                    Jsonb(predicate_results),"comparison-v1",Jsonb({"deterministic": True}),
                ),
            )
            finding_id = cursor.fetchone()["id"]
            connection.commit()
            return finding_id
