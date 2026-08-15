from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database import get_connection
from app.impact_analysis.repositories.analysis import AnalysisRunNotFoundError


CATEGORY_SQL = """
case
  when requirement_type in ('API_CONTRACT','EXECUTION_PATH') then 'INTEGRATION'
  when requirement_type in ('DATA_PERSISTENCE','DATABASE_CHANGE') then 'DATA'
  when requirement_type='TEST_COVERAGE' then 'TESTING'
  when requirement_type='SECURITY' then 'SECURITY'
  when requirement_type='DEPENDENCY' then 'DEPENDENCY'
  when requirement_type='CONFIGURATION' then 'OPERATIONAL'
  when requirement_type='NON_FUNCTIONAL' then 'PERFORMANCE'
  else 'FUNCTIONAL'
end
"""


class ImpactContractRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def requirements(self, run_id: UUID, *, actor: str) -> list[dict[str, Any]]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            self._authorize_run(cursor, run_id, actor)
            cursor.execute(
                """
                select r.requirement_key requirement_id,r.requirement_text text,
                       r.requirement_type type,r.weight,f.status
                from impact_requirements r
                left join impact_findings f on f.requirement_id=r.id and f.run_id=r.run_id
                where r.run_id=%s order by r.requirement_key
                """,
                (run_id,),
            )
            return cursor.fetchall()

    def findings(
        self,
        run_id: UUID,
        *,
        actor: str,
        status: str | None,
        category: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            self._authorize_run(cursor, run_id, actor)
            cursor.execute(
                f"""
                with items as (
                    select f.id,f.status,f.what_present,f.what_missing,
                           f.reason_code,f.technical_reason,f.explanation,
                           f.impacts,f.recommendation,f.confidence,f.completion,
                           f.score_contribution,f.code_generation_available,
                           r.requirement_key requirement_id,
                           r.requirement_text requirement,r.requirement_type,
                           r.weight,{CATEGORY_SQL} category,
                           (select count(*) from impact_evidence e
                            where e.requirement_id=r.id) evidence_count
                    from impact_findings f
                    join impact_requirements r on r.id=f.requirement_id
                    where f.run_id=%s
                )
                select *,count(*) over() total_count from items
                where (%s::text is null or status=%s)
                  and (%s::text is null or category=%s)
                order by items.requirement_id limit %s offset %s
                """,
                (
                    run_id,status,status,category.upper() if category else None,
                    category.upper() if category else None,page_size,(page - 1) * page_size,
                ),
            )
            rows = cursor.fetchall()
            return rows, int(rows[0]["total_count"]) if rows else 0

    def finding(self, finding_id: UUID, *, actor: str) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                select f.*,r.requirement_key requirement_id,
                       r.requirement_text requirement,r.requirement_type,
                       r.weight,{CATEGORY_SQL} category,ar.project_id,
                       (select count(*) from impact_evidence e
                        where e.requirement_id=r.id) evidence_count
                from impact_findings f join impact_requirements r on r.id=f.requirement_id
                join impact_analysis_runs ar on ar.id=f.run_id where f.id=%s
                """,
                (finding_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise AnalysisRunNotFoundError(str(finding_id))
            self._authorize_project(cursor, row["project_id"], actor)
            return row

    def evidence(self, finding_id: UUID, *, actor: str) -> list[dict[str, Any]]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select e.id evidence_id,e.evidence_type type,e.direction,
                       e.file_path,e.symbol,e.start_line,e.end_line,e.retrieval_method,
                       e.rank,e.score,e.description,e.excerpt,e.metadata,
                       e.source_ref repository,rs.commit_sha,f.status supports,
                       e.metadata->>'document_id' document_id,
                       e.metadata->>'document_name' document_name,
                       e.metadata->>'section' section,ar.project_id
                from impact_evidence e
                join impact_findings f on f.requirement_id=e.requirement_id
                                  and f.run_id=e.run_id
                join impact_analysis_runs ar on ar.id=e.run_id
                left join repository_snapshots rs on rs.id=e.snapshot_id
                where f.id=%s order by e.rank nulls last,e.id
                """,
                (finding_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(
                    "select ar.project_id from impact_findings f join impact_analysis_runs ar on ar.id=f.run_id where f.id=%s",
                    (finding_id,),
                )
                found = cursor.fetchone()
                if not found:
                    raise AnalysisRunNotFoundError(str(finding_id))
                self._authorize_project(cursor, found["project_id"], actor)
                return []
            self._authorize_project(cursor, rows[0]["project_id"], actor)
            return rows

    def observability(self, run_id: UUID, *, actor: str) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            self._authorize_run(cursor, run_id, actor)
            cursor.execute(
                """
                select project_id,release_id,snapshot_id
                from impact_analysis_runs where id=%s
                """,
                (run_id,),
            )
            run = cursor.fetchone()
            cursor.execute(
                """
                select count(*)::integer total_chunks,
                       count(*) filter (where embedding is not null)::integer embedded_chunks,
                       count(*) filter (where search_vector is not null)::integer searchable_chunks,
                       max(embedding_model) embedding_model,
                       max(embedding_dimensions)::integer embedding_dimensions
                from repository_source_chunks where snapshot_id=%s
                """,
                (run["snapshot_id"],),
            )
            repository = cursor.fetchone()
            cursor.execute(
                """
                select count(distinct d.doc_id)::integer documents,
                       count(c.id)::integer total_chunks,
                       count(c.id) filter (
                           where c.embedding_status='COMPLETED'
                       )::integer embedded_chunks,
                       max(c.embedding_model) embedding_model,
                       max(c.embedding_dimensions)::integer embedding_dimensions
                from documents d
                left join document_chunks c on c.doc_id=d.doc_id
                where d.project_id=%s
                  and (d.release_id is null or %s::uuid is null or d.release_id=%s)
                """,
                (run["project_id"], run["release_id"], run["release_id"]),
            )
            knowledge = cursor.fetchone()
            cursor.execute(
                """
                select evidence_type,retrieval_method,score,metadata
                from impact_evidence where run_id=%s
                """,
                (run_id,),
            )
            evidence = cursor.fetchall()

        method_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        scores: list[float] = []
        for item in evidence:
            type_counts[str(item["evidence_type"])] += 1
            methods = (item.get("metadata") or {}).get("retrieval_methods") or [
                item["retrieval_method"]
            ]
            method_counts.update(str(method) for method in methods)
            score = self._number(item.get("score"))
            if score is not None:
                scores.append(score)

        repository_total = int(repository.get("total_chunks") or 0)
        repository_embedded = int(repository.get("embedded_chunks") or 0)
        knowledge_total = int(knowledge.get("total_chunks") or 0)
        knowledge_embedded = int(knowledge.get("embedded_chunks") or 0)
        return {
            "run_id": str(run_id),
            "postgres": {
                "status": "READY",
                "repository_index": {
                    **repository,
                    "vector_status": (
                        "READY" if repository_embedded else "NOT_INDEXED"
                    ),
                    "embedding_coverage_percent": (
                        round(repository_embedded / repository_total * 100, 2)
                        if repository_total else 0
                    ),
                },
                "knowledge_base": {
                    **knowledge,
                    "vector_status": (
                        "READY" if knowledge_embedded else "NOT_INDEXED"
                    ),
                    "embedding_coverage_percent": (
                        round(knowledge_embedded / knowledge_total * 100, 2)
                        if knowledge_total else 0
                    ),
                },
            },
            "retrieval": {
                "persisted_evidence": len(evidence),
                "method_counts": dict(method_counts),
                "evidence_type_counts": dict(type_counts),
                "average_score": (
                    round(sum(scores) / len(scores), 6) if scores else None
                ),
                "maximum_score": max(scores) if scores else None,
                "rejected_candidates": None,
            },
            "instrumentation": {
                "stage_durations": False,
                "rejected_candidates": False,
                "llm_tokens": False,
                "llm_latency": False,
                "prompt_body": False,
            },
        }

    def history(
        self,
        *,
        product_space_id: UUID,
        project_id: UUID,
        scope_type: str | None,
        scope_id: UUID | None,
        page: int,
        page_size: int,
        actor: str,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            self._authorize_project(cursor, project_id, actor)
            cursor.execute(
                "select 1 from projects where id=%s and product_space_id=%s and archived_at is null",
                (project_id, product_space_id),
            )
            if not cursor.fetchone():
                raise ValueError("Project does not belong to the selected Product Space.")
            cursor.execute(
                """
                select r.*,f.feature_key,f.title feature_title,
                       us.story_key,us.title story_title,
                       gr.full_name repository_name,rs.branch,rs.commit_sha,
                       count(*) over() total_count
                from impact_analysis_runs r
                left join features f on r.scope_type='FEATURE' and f.id=r.scope_id
                left join user_stories us on r.scope_type='USER_STORY' and us.id=r.scope_id
                join project_github_repositories pgr on pgr.id=r.project_repository_id
                join github_repositories gr on gr.id=pgr.repository_id
                left join repository_snapshots rs on rs.id=r.snapshot_id
                where r.product_space_id=%s and r.project_id=%s
                  and (%s::text is null or r.scope_type=%s)
                  and (%s::uuid is null or r.scope_id=%s)
                order by r.created_at desc limit %s offset %s
                """,
                (
                    product_space_id,project_id,scope_type,scope_type,scope_id,scope_id,
                    page_size,(page - 1) * page_size,
                ),
            )
            rows = cursor.fetchall()
            return rows, int(rows[0]["total_count"]) if rows else 0

    def link_reanalysis(self, current_run_id: UUID, baseline_run_id: UUID) -> None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "update impact_analysis_runs set previous_run_id=%s,updated_at=now() where id=%s",
                (baseline_run_id, current_run_id),
            )
            connection.commit()

    def comparison(
        self, current_run_id: UUID, baseline_run_id: UUID, *, actor: str
    ) -> dict[str, Any]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select id,project_id,scope_type,scope_id,score,decomposition_version,
                       comparison_version,scoring_version,status
                from impact_analysis_runs where id in (%s,%s)
                """,
                (current_run_id, baseline_run_id),
            )
            rows = {row["id"]: row for row in cursor.fetchall()}
            if current_run_id not in rows or baseline_run_id not in rows:
                raise AnalysisRunNotFoundError("Comparison run not found")
            current = rows[current_run_id]
            baseline = rows[baseline_run_id]
            self._authorize_project(cursor, current["project_id"], actor)
            self._authorize_project(cursor, baseline["project_id"], actor)
            if (
                current["project_id"],current["scope_type"],current["scope_id"]
            ) != (
                baseline["project_id"],baseline["scope_type"],baseline["scope_id"]
            ):
                raise ValueError("Runs do not have a compatible Project and scope.")
            comparable = all(
                current[key] == baseline[key]
                for key in ("decomposition_version", "comparison_version", "scoring_version")
            )
            cursor.execute(
                """
                select coalesce(cr.requirement_key,br.requirement_key) requirement_id,
                       coalesce(cr.requirement_text,br.requirement_text) requirement,
                       bf.status previous_status,cf.status new_status
                from impact_requirements br
                full join impact_requirements cr
                  on cr.run_id=%s and br.run_id=%s
                 and cr.requirement_key=br.requirement_key
                left join impact_findings bf on bf.requirement_id=br.id
                left join impact_findings cf on cf.requirement_id=cr.id
                where (br.run_id=%s or br.run_id is null)
                  and (cr.run_id=%s or cr.run_id is null)
                order by requirement_id
                """,
                (current_run_id,baseline_run_id,baseline_run_id,current_run_id),
            )
            changes = cursor.fetchall()
        previous_score = self._number(baseline["score"]) if comparable else None
        new_score = self._number(current["score"]) if comparable else None
        return {
            "baseline_run_id": baseline_run_id,
            "current_run_id": current_run_id,
            "previous_score": previous_score,
            "new_score": new_score,
            "score_delta": (
                round(new_score - previous_score, 4)
                if previous_score is not None and new_score is not None else None
            ),
            "requirement_changes": [
                {**row, "change": self._change(row, comparable)} for row in changes
            ],
        }

    @staticmethod
    def _change(row: dict[str, Any], comparable: bool) -> str:
        if not comparable:
            return "INCOMPARABLE"
        old, new = row["previous_status"], row["new_status"]
        if old is None:
            return "ADDED"
        if new is None:
            return "REMOVED"
        if old == new:
            return "UNCHANGED"
        rank = {"MISSING": 0, "PARTIAL": 1, "PRESENT": 2}
        if old == "UNKNOWN" or new == "UNKNOWN":
            return "INCOMPARABLE"
        if new == "PRESENT" and old != "PRESENT":
            return "RESOLVED"
        return "IMPROVED" if rank[new] > rank[old] else "REGRESSED"

    @staticmethod
    def _number(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float, Decimal)) else None

    def _authorize_run(self, cursor, run_id: UUID, actor: str) -> None:
        cursor.execute("select project_id from impact_analysis_runs where id=%s", (run_id,))
        row = cursor.fetchone()
        if not row:
            raise AnalysisRunNotFoundError(str(run_id))
        self._authorize_project(cursor, row["project_id"], actor)

    @staticmethod
    def _authorize_project(cursor, project_id: UUID, actor: str) -> None:
        try:
            actor_id = UUID(actor)
        except ValueError:
            # This value is issued only by the opt-in loopback development gate.
            return
        cursor.execute(
            "select 1 from project_members where project_id=%s and user_id=%s",
            (project_id, actor_id),
        )
        if not cursor.fetchone():
            raise PermissionError("Actor is not a member of the Project.")
