from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.impact_analysis.enums import (
    EvidenceDirection,
    EvidenceType,
    FindingStatus,
    GraphNodeType,
    GraphRelationshipType,
    PredicateResult,
    ReasonCode,
    RetrievalMethod,
)
from app.impact_analysis.schemas import (
    EvidenceRecord,
    GraphEdge,
    GraphNode,
    GraphResponse,
    LLMComparisonCandidate,
    StartAnalysisRequest,
)
from app.impact_analysis.validators import (
    classify_predicates,
    validate_evidence_references,
)


def test_start_request_rejects_control_characters_and_unknown_fields() -> None:
    values = {
        "product_space_id": uuid4(),
        "project_id": uuid4(),
        "scope_type": "USER_STORY",
        "scope_id": uuid4(),
        "project_repository_id": uuid4(),
        "ref": "main\nmalicious",
        "client_request_id": uuid4(),
    }
    with pytest.raises(ValidationError):
        StartAnalysisRequest.model_validate(values)
    values["ref"] = "main"
    values["unexpected"] = True
    with pytest.raises(ValidationError):
        StartAnalysisRequest.model_validate(values)


def test_source_evidence_requires_commit_file_and_valid_span() -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id=uuid4(),
            requirement_id=uuid4(),
            type=EvidenceType.SOURCE_CODE,
            direction=EvidenceDirection.SUPPORTS,
            retrieval_method=RetrievalMethod.STRUCTURED_SYMBOL,
            description="A matching symbol was found.",
        )
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id=uuid4(),
            requirement_id=uuid4(),
            type=EvidenceType.SOURCE_CODE,
            direction=EvidenceDirection.SUPPORTS,
            retrieval_method=RetrievalMethod.STRUCTURED_SYMBOL,
            commit_sha="abc1234",
            file_path="app/service.py",
            start_line=10,
            end_line=9,
            description="Invalid source range.",
        )


def test_status_reason_pair_is_enforced() -> None:
    with pytest.raises(ValidationError):
        LLMComparisonCandidate(
            requirement_id=uuid4(),
            candidate_status=FindingStatus.MISSING,
            confidence=0.8,
            reason_code=ReasonCode.IMPLEMENTED,
            technical_reason="No proof was supplied.",
            explanation="The evidence is insufficient.",
            recommendation="Review the implementation.",
        )


def test_unknown_evidence_references_are_rejected() -> None:
    known = uuid4()
    with pytest.raises(ValueError, match="Unknown evidence IDs"):
        validate_evidence_references([known, uuid4()], {known})


@pytest.mark.parametrize(
    ("results", "coverage", "expected"),
    [
        ([PredicateResult.PROVEN], True, FindingStatus.PRESENT),
        (
            [PredicateResult.PROVEN, PredicateResult.NOT_PROVEN],
            True,
            FindingStatus.PARTIAL,
        ),
        ([PredicateResult.NOT_PROVEN], True, FindingStatus.MISSING),
        ([PredicateResult.NOT_PROVEN], False, FindingStatus.UNKNOWN),
        ([PredicateResult.UNKNOWN], True, FindingStatus.UNKNOWN),
    ],
)
def test_predicate_classification(results, coverage, expected) -> None:
    assert classify_predicates(results, coverage_sufficient=coverage) == expected


def test_graph_rejects_missing_endpoint_and_unproven_inferred_edge() -> None:
    node = GraphNode(id="n1", type=GraphNodeType.REQUIREMENT, label="Requirement")
    with pytest.raises(ValidationError):
        GraphResponse(
            nodes=[node],
            edges=[
                GraphEdge(
                    id="e1",
                    type=GraphRelationshipType.REQUIRES,
                    source="n1",
                    target="missing",
                )
            ],
        )
    with pytest.raises(ValidationError):
        GraphResponse(
            nodes=[
                node,
                GraphNode(id="n2", type=GraphNodeType.SERVICE, label="Service"),
            ],
            edges=[
                GraphEdge(
                    id="e2",
                    type=GraphRelationshipType.REQUIRES,
                    source="n1",
                    target="n2",
                    inferred=True,
                )
            ],
        )
