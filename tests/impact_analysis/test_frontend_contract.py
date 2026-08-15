from datetime import UTC, datetime
from decimal import Decimal
import inspect
from uuid import uuid4

from app.impact_analysis.graph.contract_view import ImpactGraphContractView
from app.impact_analysis.presenters import (
    present_evidence,
    present_finding,
    present_generated_change,
    present_requirement,
    present_run,
)
from app.impact_analysis.repositories.contract_queries import ImpactContractRepository


def test_run_presenter_matches_frontend_polling_contract() -> None:
    run_id = uuid4()
    row = {
        "id": run_id,
        "status": "COMPLETED",
        "stage": "COMPLETED",
        "progress_percent": 100,
        "message": "Analysis completed",
        "created_at": datetime.now(UTC),
        "started_at": datetime.now(UTC),
        "completed_at": datetime.now(UTC),
        "score": Decimal("72.5000"),
        "scope_type": "USER_STORY",
        "scope_id": uuid4(),
        "story_key": "CSA-102",
        "story_title": "Cache retrieval",
        "feature_key": None,
        "feature_title": None,
        "snapshot_id": uuid4(),
        "project_repository_id": uuid4(),
        "repository_name": "example/backend",
        "branch": "main",
        "commit_sha": "a" * 40,
        "present_count": 3,
        "partial_count": 1,
        "missing_count": 1,
        "unknown_count": 1,
        "previous_run_id": uuid4(),
    }
    result = present_run(row)
    assert result["run_id"] == str(run_id)
    assert result["repository"]["repository_id"] == str(row["project_repository_id"])
    assert result["repository"]["commit_sha"] == "a" * 40
    assert result["counts"] == {"present": 3, "partial": 1, "missing": 1, "unknown": 1}
    assert result["timeline"][-1] == {
        "stage": "COMPLETED",
        "label": "Complete analysis",
        "status": "COMPLETED",
        "progress_percent": 100,
        "message": "Analysis completed",
    }
    assert result["error"] is None


def test_queued_run_does_not_emit_incomplete_repository_object() -> None:
    result = present_run(
        {
            "id": uuid4(),
            "status": "QUEUED",
            "stage": "SCOPE_RESOLUTION",
            "progress_percent": 0,
            "scope_type": "FEATURE",
            "scope_id": uuid4(),
            "snapshot_id": None,
        }
    )
    assert result["repository"] is None
    assert result["scope"] is None


def test_failed_run_exposes_failed_backend_step_and_error() -> None:
    result = present_run(
        {
            "id": uuid4(),
            "status": "FAILED",
            "stage": "FAILED",
            "progress_percent": 34,
            "message": "Analysis failed",
            "error_code": "UNIQUEVIOLATION",
            "error_message": (
                "duplicate key violates repository_source_edges_snapshot_id_edge_key_key"
            ),
            "scope_type": "FEATURE",
            "scope_id": uuid4(),
            "snapshot_id": None,
        }
    )

    failed = next(item for item in result["timeline"] if item["status"] == "FAILED")
    assert failed["stage"] == "SOURCE_INDEXING"
    assert result["error"] == {
        "code": "UNIQUEVIOLATION",
        "message": (
            "duplicate key violates repository_source_edges_snapshot_id_edge_key_key"
        ),
        "stage": "SOURCE_INDEXING",
    }


def test_requirement_finding_and_evidence_presenters_use_public_ids() -> None:
    requirement = present_requirement(
        {
            "requirement_id": "REQ-002",
            "text": "Cache must exist",
            "type": "COMPONENT_EXISTENCE",
            "weight": Decimal("0.2"),
            "status": "PARTIAL",
        }
    )
    finding = present_finding(
        {
            "id": uuid4(),
            "requirement_id": "REQ-002",
            "requirement": "Cache must exist",
            "category": "FUNCTIONAL",
            "status": "PARTIAL",
            "impacts": [{"summary": "Repeated work may occur."}],
            "confidence": Decimal("0.9"),
            "weight": Decimal("0.2"),
            "completion": Decimal("0.5"),
            "score_contribution": Decimal("10"),
            "evidence_count": 1,
            "code_generation_available": True,
        }
    )
    evidence = present_evidence(
        {
            "evidence_id": uuid4(),
            "type": "SOURCE_CODE",
            "description": "Cache client exists.",
            "supports": "PARTIAL",
            "direction": "SUPPORTS",
            "rank": 1,
            "score": Decimal("0.92"),
            "excerpt": "cache = CacheClient()",
            "metadata": {"retrieval_methods": ["KEYWORD_FTS"]},
        }
    )
    assert requirement["requirement_id"] == "REQ-002"
    assert finding["requirement_id"] == "REQ-002"
    assert finding["impact"] == "Repeated work may occur."
    assert evidence["description"] == "Cache client exists."
    assert evidence["score"] == 0.92
    assert evidence["retrieval_methods"] == ["KEYWORD_FTS"]
    assert evidence["excerpt"] == "cache = CacheClient()"


def test_generated_change_presenter_matches_frontend_schema() -> None:
    result = present_generated_change(
        {
            "id": uuid4(),
            "finding_id": uuid4(),
            "status": "REQUESTED",
            "repository_name": "example/backend",
            "base_ref": "main",
            "base_commit_sha": "a" * 40,
            "created_at": datetime.now(UTC),
            "proposed_files": [],
            "validations": [],
        }
    )
    assert result["status"] == "QUEUED"
    assert result["repository"] == "example/backend"
    assert result["files"] == []
    assert result["validation"] == {"status": "NOT_STARTED", "checks": []}


def test_graph_contract_includes_edge_endpoints() -> None:
    class Neo4jTemporal:
        def iso_format(self):
            return "2026-08-09T20:22:42Z"

    class Client:
        def execute_read(self, query, parameters):
            self.query = query
            return [
                {
                    "source_properties": {
                        "display_label": "Service",
                        "node_type": "SERVICE",
                        "truth_side": "ACTUAL",
                        "observed_at": Neo4jTemporal(),
                    },
                    "source_id": "service:one",
                    "relationship_type": "CALLS",
                    "relationship": {"id": "edge:one"},
                    "target_properties": {
                        "display_label": "Function",
                        "node_type": "FUNCTION",
                        "truth_side": "ACTUAL",
                    },
                    "target_id": "function:one",
                }
            ]

    client = Client()
    graph = ImpactGraphContractView(client).get(run_id=str(uuid4()), view="actual")
    assert graph["edges"][0]["source"] == "service:one"
    assert graph["edges"][0]["target"] == "function:one"
    assert {node["id"] for node in graph["nodes"]} == {"service:one", "function:one"}
    service = next(node for node in graph["nodes"] if node["id"] == "service:one")
    assert service["metadata"]["observed_at"] == "2026-08-09T20:22:42Z"
    assert "AS source_properties" in client.query
    assert "AS target_properties" in client.query


def test_comparison_change_classification() -> None:
    classify = ImpactContractRepository._change
    assert classify({"previous_status": "PARTIAL", "new_status": "PRESENT"}, True) == "RESOLVED"
    assert classify({"previous_status": "PRESENT", "new_status": "MISSING"}, True) == "REGRESSED"
    assert classify({"previous_status": None, "new_status": "PRESENT"}, True) == "ADDED"
    assert classify({"previous_status": "PRESENT", "new_status": "PRESENT"}, False) == "INCOMPARABLE"


def test_local_analysis_actor_skips_membership_query() -> None:
    class Cursor:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("Local analysis actors must not query project_members")

    ImpactContractRepository._authorize_project(
        Cursor(), uuid4(), "local-impact-analysis"
    )


def test_history_types_optional_scope_filters_for_postgres() -> None:
    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, parameters):
            self.statements.append((statement, parameters))

        def fetchone(self):
            return {"id": uuid4()}

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self._cursor

    cursor = Cursor()
    repository = ImpactContractRepository(lambda: Connection(cursor))
    rows, total = repository.history(
        product_space_id=uuid4(),
        project_id=uuid4(),
        scope_type=None,
        scope_id=None,
        page=1,
        page_size=20,
        actor="local-impact-analysis",
    )

    history_sql = cursor.statements[-1][0]
    assert "%s::text is null" in history_sql
    assert "%s::uuid is null" in history_sql
    assert rows == []
    assert total == 0


def test_findings_query_uses_unique_columns_and_typed_filters() -> None:
    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, parameters):
            self.statements.append((statement, parameters))

        def fetchone(self):
            return {"project_id": uuid4()}

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self._cursor

    cursor = Cursor()
    repository = ImpactContractRepository(lambda: Connection(cursor))
    rows, total = repository.findings(
        uuid4(),
        actor="local-impact-analysis",
        status=None,
        category=None,
        page=1,
        page_size=200,
    )

    findings_sql = cursor.statements[-1][0]
    assert "select f.*" not in findings_sql
    assert findings_sql.count("%s::text is null") == 2
    assert "order by items.requirement_id" in findings_sql
    assert rows == []
    assert total == 0


def test_all_frontend_required_backend_routes_are_registered() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    required = {
        ("get", "/api/v1/workspace"),
        ("get", "/api/v1/projects/{project_id}/planning-options"),
        ("get", "/api/v1/github/repositories/imported"),
        ("get", "/api/v1/github/project-repositories/{project_repository_id}/branches"),
        ("post", "/api/v1/impact-analysis/runs"),
        ("get", "/api/v1/impact-analysis/runs/{run_id}"),
        ("get", "/api/v1/impact-analysis/runs/{run_id}/requirements"),
        ("get", "/api/v1/impact-analysis/runs/{run_id}/observability"),
        ("get", "/api/v1/impact-analysis/runs/{run_id}/findings"),
        ("get", "/api/v1/impact-analysis/findings/{finding_id}"),
        ("get", "/api/v1/impact-analysis/findings/{finding_id}/evidence"),
        ("get", "/api/v1/impact-analysis/runs/{run_id}/graph"),
        ("get", "/api/v1/impact-analysis/history"),
        (
            "post",
            "/api/v1/impact-analysis/runs/{run_id}/findings/{finding_id}/remediation-prompt",
        ),
        ("post", "/api/v1/impact-analysis/findings/{finding_id}/generated-changes"),
        ("get", "/api/v1/impact-analysis/generated-changes/{change_id}"),
        ("post", "/api/v1/impact-analysis/generated-changes/{change_id}/validate"),
        ("post", "/api/v1/impact-analysis/generated-changes/{change_id}/approve"),
        ("post", "/api/v1/impact-analysis/generated-changes/{change_id}/pull-request"),
        ("post", "/api/v1/impact-analysis/runs/{run_id}/reanalyze"),
        ("get", "/api/v1/impact-analysis/runs/{run_id}/comparison"),
    }
    assert all(method in paths[path] for method, path in required)


def test_analysis_background_entrypoint_runs_in_threadpool() -> None:
    from app.routes.impact_contract import process_analysis_in_background

    assert inspect.iscoroutinefunction(process_analysis_in_background) is False
