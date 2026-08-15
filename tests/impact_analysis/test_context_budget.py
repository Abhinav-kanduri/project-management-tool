from uuid import uuid4

from app.impact_analysis.context import ContextBuilder
from app.impact_analysis.domain import DesignEvidenceItem, DesignEvidencePackage
from app.impact_analysis.enums import RequirementType
from app.impact_analysis.schemas import (
    AtomicRequirement,
    ExpectedPredicate,
    RequirementProvenance,
)


def test_design_and_source_context_share_one_character_budget(requirement_package) -> None:
    requirement = AtomicRequirement(
        requirement_id=uuid4(),
        requirement_key="REQ-001",
        text="A cache service must exist",
        type=RequirementType.COMPONENT_EXISTENCE,
        weight=1,
        provenance=[RequirementProvenance(source_type="FEATURE", source_id="FEATURE:1")],
        expected_predicates=[
            ExpectedPredicate(
                predicate_id="PRED-001", predicate_type="EXISTS", subject="cache service"
            )
        ],
    )
    design = DesignEvidencePackage(
        project_id=requirement_package.project.project_id,
        query="cache",
        items=[
            DesignEvidenceItem(
                document_id="document",
                document_name="ARCHITECTURE.md",
                document_type="MARKDOWN",
                chunk_id="chunk",
                chunk_index=0,
                text="x" * 100,
                approval_basis="ARCHITECTURE_NAME_OR_ROLE",
            )
        ],
    )
    context = ContextBuilder(max_total_chars=30).build(
        requirement=requirement,
        package=requirement_package,
        design=design,
        candidates=[],
        snapshot={
            "id": uuid4(),
            "branch": "main",
            "commit_sha": "abc",
            "coverage_percent": 100,
        },
    )
    assert len(context.design_evidence[0]["text"]) == 30
    assert context.truncated is True
