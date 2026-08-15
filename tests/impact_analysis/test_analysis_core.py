from uuid import uuid4

import pytest

from app.impact_analysis.comparison import DeterministicComparator
from app.impact_analysis.context import AnalysisContext, ContextBuilder
from app.impact_analysis.domain import DesignEvidencePackage
from app.impact_analysis.enums import (
    FindingStatus,
    RequirementApplicability,
    RequirementType,
    RetrievalMethod,
)
from app.impact_analysis.retrieval.models import RetrievalCandidate
from app.impact_analysis.schemas import (
    AtomicRequirement,
    ExpectedPredicate,
    RequirementProvenance,
)
from app.impact_analysis.scoring import calculate_score
from app.impact_analysis.services.evidence import EvidenceMaterializer


def requirement(
    text: str,
    *,
    applicability: RequirementApplicability = RequirementApplicability.STATICALLY_VERIFIABLE,
) -> AtomicRequirement:
    return AtomicRequirement(
        requirement_id=uuid4(),
        requirement_key="REQ-001",
        text=text,
        type=RequirementType.COMPONENT_EXISTENCE,
        applicability=applicability,
        weight=1,
        provenance=[
            RequirementProvenance(source_type="FEATURE", source_id="FEATURE:1")
        ],
        expected_predicates=[
            ExpectedPredicate(
                predicate_id="PRED-001",
                predicate_type="EXISTS",
                subject=text,
            )
        ],
    )


def source_candidate(text: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_key="chunk:one",
        method=RetrievalMethod.KEYWORD_FTS,
        snapshot_id=uuid4(),
        file_id=uuid4(),
        file_path="app/services/cache.py",
        symbol_id=uuid4(),
        symbol="RedisCache.get",
        chunk_id=uuid4(),
        start_line=10,
        end_line=20,
        content=text,
        content_sha256="a" * 64,
        source_score=0.8,
        fused_score=0.04,
        rank=1,
    )


def context_for(item: AtomicRequirement, *, coverage: float) -> AnalysisContext:
    return AnalysisContext(
        requirement=item,
        project={"id": "one"},
        scope={"id": "two"},
        design_evidence=[],
        source_evidence=[],
        repository={"commit_sha": "abc"},
        retrieval_coverage_percent=coverage,
    )


def evidence_for(item: AtomicRequirement, candidate: RetrievalCandidate):
    return EvidenceMaterializer().materialize(
        run_id=uuid4(),
        requirement_id=item.requirement_id,
        repository="example/repository",
        commit_sha="abc123",
        candidates=[candidate],
    )


def test_score_excludes_unknown_and_weights_partial() -> None:
    result = calculate_score(
        [
            (FindingStatus.PRESENT, 0.25),
            (FindingStatus.PARTIAL, 0.25),
            (FindingStatus.MISSING, 0.25),
            (FindingStatus.UNKNOWN, 0.25),
        ]
    )
    assert result.score == pytest.approx(50)
    assert result.applicable_weight == pytest.approx(0.75)
    assert result.excluded_weight == pytest.approx(0.25)
    assert result.contributions[-1] is None


@pytest.mark.parametrize(
    ("text", "source", "coverage", "expected"),
    [
        ("Redis cache service", "class RedisCacheService", 100, FindingStatus.PRESENT),
        (
            "Redis caching persistence workflow",
            "redis client",
            100,
            FindingStatus.PARTIAL,
        ),
    ],
)
def test_comparator_uses_repository_evidence(
    text: str, source: str, coverage: float, expected: FindingStatus
) -> None:
    item = requirement(text)
    evidence = evidence_for(item, source_candidate(source))
    result = DeterministicComparator().compare(
        context=context_for(item, coverage=coverage), evidence=evidence
    )
    assert result.candidate.candidate_status == expected
    assert result.candidate.evidence_ids == [evidence[0].evidence_id]


def test_comparator_does_not_claim_missing_when_coverage_is_incomplete() -> None:
    item = requirement("Redis caching persistence workflow")
    result = DeterministicComparator().compare(
        context=context_for(item, coverage=50), evidence=[]
    )
    assert result.candidate.candidate_status == FindingStatus.UNKNOWN


def test_runtime_requirement_is_unknown_even_with_source() -> None:
    item = requirement(
        "Responses within 500 milliseconds",
        applicability=RequirementApplicability.RUNTIME_EVIDENCE_REQUIRED,
    )
    evidence = evidence_for(item, source_candidate("timeout = 0.5"))
    result = DeterministicComparator().compare(
        context=context_for(item, coverage=100), evidence=evidence
    )
    assert result.candidate.candidate_status == FindingStatus.UNKNOWN


def test_context_builder_enforces_candidate_and_character_budgets(
    requirement_package,
) -> None:
    item = requirement("Redis cache service")
    candidates = [
        source_candidate("x" * 100).model_copy(update={"candidate_key": f"chunk:{index}"})
        for index in range(4)
    ]
    context = ContextBuilder(
        max_candidates=2, max_excerpt_chars=20, max_total_chars=30
    ).build(
        requirement=item,
        package=requirement_package,
        design=DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="redis",
        ),
        candidates=candidates,
        snapshot={
            "id": uuid4(),
            "branch": "main",
            "commit_sha": "abc123",
            "coverage_percent": 100,
        },
    )
    assert context.truncated is True
    assert len(context.source_evidence) == 2
    assert sum(len(item.excerpt) for item in context.source_evidence) == 30


def test_impact_api_allows_optional_actor_only_for_analysis_routes() -> None:
    from app.main import app

    operation = app.openapi()["paths"]["/api/v1/impact-analysis/runs"]["post"]
    actor = next(
        parameter for parameter in operation["parameters"] if parameter["name"] == "X-Actor"
    )
    assert actor["required"] is False

    prompt = app.openapi()["paths"][
        "/api/v1/impact-analysis/runs/{run_id}/findings/{finding_id}/remediation-prompt"
    ]["post"]
    prompt_actor = next(
        parameter for parameter in prompt["parameters"] if parameter["name"] == "X-Actor"
    )
    assert prompt_actor["required"] is False

    remediation = app.openapi()["paths"][
        "/api/v1/impact-analysis/findings/{finding_id}/generated-changes"
    ]["post"]
    remediation_actor = next(
        parameter
        for parameter in remediation["parameters"]
        if parameter["name"] == "X-Actor"
    )
    assert remediation_actor["required"] is True
    assert remediation_actor["schema"]["format"] == "uuid"


def test_anonymous_analysis_actor_is_opt_in_and_loopback_only(monkeypatch) -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.routes import impact_contract

    monkeypatch.setattr(impact_contract, "ALLOW_LOCAL_ANONYMOUS_ANALYSIS", True)
    local = Request({"type": "http", "client": ("127.0.0.1", 43100)})
    assert (
        impact_contract.resolve_analysis_actor(local, None)
        == impact_contract.LOCAL_ANALYSIS_ACTOR
    )

    remote = Request({"type": "http", "client": ("192.0.2.10", 43100)})
    with pytest.raises(HTTPException) as error:
        impact_contract.resolve_analysis_actor(remote, None)
    assert error.value.status_code == 401
