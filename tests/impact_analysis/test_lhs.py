import re

from uuid import uuid4

import pytest

from app.impact_analysis.domain import (
    DesignEvidencePackage,
    RequirementCandidate,
    RequirementCandidateSet,
)
from app.impact_analysis.enums import (
    GraphNodeType,
    GraphRelationshipType,
    RequirementApplicability,
    RequirementType,
)
from app.impact_analysis.graph.expected_builder import ExpectedGraphBuilder
from app.impact_analysis.graph.repository import ImpactGraphRepository
from app.impact_analysis.services.requirement_decomposer import (
    RequirementDecomposer,
    RequirementValidationError,
)
from app.impact_analysis.services.scope_resolver import ScopeResolver


def test_scope_resolver_delegates_authoritative_ids(requirement_package) -> None:
    class Repository:
        def load(self, **values):
            assert values["project_id"] == requirement_package.project.project_id
            assert values["scope_id"] == requirement_package.scope_id
            return requirement_package

    result = ScopeResolver(Repository()).resolve(
        actor="local-user",
        product_space_id=requirement_package.project.product_space_id,
        project_id=requirement_package.project.project_id,
        release_id=requirement_package.release_id,
        scope_type=requirement_package.scope_type,
        scope_id=requirement_package.scope_id,
        project_repository_id=requirement_package.repository.project_repository_id,
    )
    assert result.user_story.story_key == "CSA-102"


def test_deterministic_decomposition_is_traceable_and_runtime_aware(
    requirement_package,
) -> None:
    design = DesignEvidencePackage(
        project_id=requirement_package.project.project_id,
        query="router rag redis",
    )
    requirements = RequirementDecomposer().decompose(requirement_package, design)
    assert requirements
    assert [item.requirement_key for item in requirements] == [
        f"REQ-{index:03d}" for index in range(1, len(requirements) + 1)
    ]
    assert sum(item.weight for item in requirements) == pytest.approx(1)
    assert all(item.provenance for item in requirements)
    performance = [
        item for item in requirements if "milliseconds" in item.text.casefold()
    ][0]
    assert performance.applicability == RequirementApplicability.RUNTIME_EVIDENCE_REQUIRED


def test_deterministic_decomposition_splits_repeated_must_clauses(
    requirement_package,
) -> None:
    requirement_package.feature.functional_requirements = [
        "Chat is read-only: requests that intend to mutate project state must not perform persistence and must return guidance directing users to the Dashboard or Project Management API for mutations."
    ]
    requirement_package.feature.non_functional_requirements = []
    requirement_package.acceptance_criteria = []
    requirement_package.user_story = None

    requirements = RequirementDecomposer().decompose(
        requirement_package,
        DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="read-only chat",
        ),
    )

    matching = [
        item.text
        for item in requirements
        if "mutate project state" in item.text.casefold()
    ]
    assert matching == [
        "Chat is read-only: requests that intend to mutate project state must not perform persistence",
        "Chat is read-only: requests that intend to mutate project state must return guidance directing users to the Dashboard or Project Management API for mutations.",
    ]
    assert all(len(re.findall(r"\bmust\b", item, re.I)) == 1 for item in matching)


@pytest.mark.parametrize(
    "requirement",
    [
        "this must be observable in logs/metrics and the session must be distinct from a session with the same S but a different X-Actor.",
        "this must be observable in logs/metrics and the sessionmust be distinct from a session with the same S but a different X-Actor.",
    ],
)
def test_deterministic_decomposition_splits_repeated_must_with_new_subject(
    requirement_package,
    requirement,
) -> None:
    requirement_package.feature.functional_requirements = [requirement]
    requirement_package.feature.non_functional_requirements = []
    requirement_package.acceptance_criteria = []
    requirement_package.user_story = None

    requirements = RequirementDecomposer().decompose(
        requirement_package,
        DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="session identity observability",
        ),
    )

    assert [item.text for item in requirements] == [
        "this must be observable in logs/metrics",
        "the session must be distinct from a session with the same S but a different X-Actor.",
    ]
    assert all(
        len(re.findall(r"\bmust\b", item.text, re.I)) == 1
        for item in requirements
    )


def test_injected_candidates_cannot_reference_unknown_sources(
    requirement_package,
) -> None:
    candidates = RequirementCandidateSet(
        requirements=[
            RequirementCandidate(
                text="Redis cache must exist",
                type=RequirementType.COMPONENT_EXISTENCE,
                source_references=["DOCUMENT:invented"],
                predicates=[
                    {
                        "predicate_type": "EXISTS",
                        "subject": "Redis cache",
                        "mandatory": True,
                    }
                ],
            )
        ]
    )
    decomposer = RequirementDecomposer(lambda package, design: candidates)
    with pytest.raises(RequirementValidationError, match="unknown sources"):
        decomposer.decompose(
            requirement_package,
            DesignEvidencePackage(
                project_id=requirement_package.project.project_id,
                query="redis",
            ),
        )


def test_decomposition_bounds_long_predicates_without_losing_requirement_text(
    requirement_package,
) -> None:
    long_requirement = (
        "An authenticated request must create a conversation record "
        + "with durable audit metadata " * 30
        + "linked by conversation_id"
    )
    requirement_package.feature.functional_requirements = [long_requirement]
    requirement_package.feature.non_functional_requirements = []
    requirement_package.acceptance_criteria = []
    requirement_package.user_story = None

    requirements = RequirementDecomposer().decompose(
        requirement_package,
        DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="authenticated conversation creation",
        ),
    )

    assert requirements[0].text == long_requirement
    assert len(requirements[0].expected_predicates[0].subject) <= 500
    assert requirements[0].expected_predicates[0].subject.endswith("...")


def test_decomposition_bounds_injected_predicate_object(requirement_package) -> None:
    feature_reference = f"FEATURE:{requirement_package.feature.id}"
    candidates = RequirementCandidateSet(
        requirements=[
            RequirementCandidate(
                text="The conversation service must persist a linked message",
                type=RequirementType.DATA_PERSISTENCE,
                source_references=[feature_reference],
                predicates=[
                    {
                        "predicate_type": "PERSISTS",
                        "subject": "conversation service",
                        "object": "linked message metadata " * 30,
                    }
                ],
            )
        ]
    )

    requirements = RequirementDecomposer(
        lambda package, design: candidates
    ).decompose(
        requirement_package,
        DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="conversation persistence",
        ),
    )

    predicate = requirements[0].expected_predicates[0]
    assert predicate.subject == "conversation service"
    assert predicate.object is not None
    assert len(predicate.object) <= 500
    assert predicate.object.endswith("...")


def test_expected_graph_is_allowlisted_and_run_scoped(requirement_package) -> None:
    run_id = uuid4()
    requirements = RequirementDecomposer().decompose(
        requirement_package,
        DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="router rag redis",
        ),
    )
    graph = ExpectedGraphBuilder().build(
        run_id=run_id,
        package=requirement_package,
        requirements=requirements,
    )
    assert {GraphNodeType.FEATURE, GraphNodeType.USER_STORY, GraphNodeType.REQUIREMENT} <= {
        node.type for node in graph.nodes
    }
    assert GraphRelationshipType.HAS_REQUIREMENT in {edge.type for edge in graph.edges}
    assert all(edge.source in {node.id for node in graph.nodes} for edge in graph.edges)
    assert any(node.properties.get("run_id") == str(run_id) for node in graph.nodes)


def test_graph_repository_groups_only_allowlisted_labels_and_edges(
    requirement_package,
) -> None:
    run_id = uuid4()
    requirements = RequirementDecomposer().decompose(
        requirement_package,
        DesignEvidencePackage(
            project_id=requirement_package.project.project_id,
            query="router",
        ),
    )
    batch = ExpectedGraphBuilder().build(
        run_id=run_id,
        package=requirement_package,
        requirements=requirements,
    )

    class Client:
        def __init__(self):
            self.writes = []

        def execute_write(self, query, parameters):
            self.writes.append((query, parameters))
            return []

    client = Client()
    ImpactGraphRepository(client).upsert(batch, run_id=str(run_id))
    assert client.writes
    assert all("UNWIND $rows" in query for query, _ in client.writes)
    assert all(parameters["rows"] for _, parameters in client.writes)
