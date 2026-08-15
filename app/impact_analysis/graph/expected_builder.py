from __future__ import annotations

import re
from uuid import UUID, uuid5

from app.impact_analysis.domain import RequirementPackage
from app.impact_analysis.enums import (
    GraphNodeType,
    GraphRelationshipType,
    RequirementType,
)
from app.impact_analysis.graph.models import GraphBatch, GraphEdge, GraphNode
from app.impact_analysis.schemas import AtomicRequirement


GRAPH_NAMESPACE = UUID("7b027d52-0ed0-4ea5-adbc-77f65d7a7598")


class ExpectedGraphBuilder:
    def build(
        self,
        *,
        run_id: UUID,
        package: RequirementPackage,
        requirements: list[AtomicRequirement],
    ) -> GraphBatch:
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        feature_id = f"feature:{package.feature.id}"
        nodes[feature_id] = GraphNode(
            id=feature_id,
            type=GraphNodeType.FEATURE,
            label=package.feature.feature_key,
            properties={
                "source_id": str(package.feature.id),
                "project_id": str(package.project.project_id),
                "title": package.feature.title,
                "truth_side": "EXPECTED",
            },
        )
        scope_node = feature_id
        if package.user_story:
            story_id = f"user-story:{package.user_story.id}"
            nodes[story_id] = GraphNode(
                id=story_id,
                type=GraphNodeType.USER_STORY,
                label=package.user_story.story_key,
                properties={
                    "source_id": str(package.user_story.id),
                    "project_id": str(package.project.project_id),
                    "title": package.user_story.title,
                    "truth_side": "EXPECTED",
                },
            )
            edge_id = f"{feature_id}:HAS_USER_STORY:{story_id}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                type=GraphRelationshipType.HAS_USER_STORY,
                source=feature_id,
                target=story_id,
            )
            scope_node = story_id

        for requirement in requirements:
            requirement_uuid = requirement.requirement_id or uuid5(
                GRAPH_NAMESPACE, f"{run_id}:{requirement.requirement_key}"
            )
            requirement_node_id = f"requirement:{requirement_uuid}"
            nodes[requirement_node_id] = GraphNode(
                id=requirement_node_id,
                type=GraphNodeType.REQUIREMENT,
                label=requirement.requirement_key,
                properties={
                    "source_id": str(requirement_uuid),
                    "run_id": str(run_id),
                    "project_id": str(package.project.project_id),
                    "requirement_key": requirement.requirement_key,
                    "text": requirement.text,
                    "requirement_type": requirement.type.value,
                    "truth_side": "EXPECTED",
                },
            )
            edge_id = f"{scope_node}:HAS_REQUIREMENT:{requirement_node_id}"
            edges[edge_id] = GraphEdge(
                id=edge_id,
                type=GraphRelationshipType.HAS_REQUIREMENT,
                source=scope_node,
                target=requirement_node_id,
            )
            for predicate in requirement.expected_predicates:
                subject_id = self._expected_target_id(
                    run_id, predicate.subject, requirement.type
                )
                nodes.setdefault(
                    subject_id,
                    GraphNode(
                        id=subject_id,
                        type=self._target_type(requirement.type, predicate.subject),
                        label=predicate.subject[:500],
                        properties={
                            "run_id": str(run_id),
                            "project_id": str(package.project.project_id),
                            "truth_side": "EXPECTED",
                            "predicate_type": predicate.predicate_type,
                        },
                    ),
                )
                requires_id = f"{requirement_node_id}:REQUIRES:{subject_id}"
                edges[requires_id] = GraphEdge(
                    id=requires_id,
                    type=GraphRelationshipType.REQUIRES,
                    source=requirement_node_id,
                    target=subject_id,
                )
                if predicate.object:
                    object_id = self._expected_target_id(
                        run_id, predicate.object, requirement.type
                    )
                    nodes.setdefault(
                        object_id,
                        GraphNode(
                            id=object_id,
                            type=self._target_type(requirement.type, predicate.object),
                            label=predicate.object[:500],
                            properties={
                                "run_id": str(run_id),
                                "project_id": str(package.project.project_id),
                                "truth_side": "EXPECTED",
                            },
                        ),
                    )
                    relationship = self._predicate_relationship(predicate.predicate_type)
                    path_id = f"{subject_id}:{relationship.value}:{object_id}"
                    edges[path_id] = GraphEdge(
                        id=path_id,
                        type=relationship,
                        source=subject_id,
                        target=object_id,
                    )
        return GraphBatch(nodes=list(nodes.values()), edges=list(edges.values()))

    @staticmethod
    def _expected_target_id(
        run_id: UUID, value: str, requirement_type: RequirementType
    ) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120]
        stable = uuid5(GRAPH_NAMESPACE, f"{run_id}:{requirement_type}:{normalized}")
        return f"expected:{stable}"

    @staticmethod
    def _target_type(requirement_type: RequirementType, value: str) -> GraphNodeType:
        lowered = value.casefold()
        if requirement_type == RequirementType.TEST_COVERAGE or "test" in lowered:
            return GraphNodeType.TEST
        if requirement_type == RequirementType.API_CONTRACT or "endpoint" in lowered:
            return GraphNodeType.API
        if requirement_type in {RequirementType.DATA_PERSISTENCE, RequirementType.DATABASE_CHANGE}:
            return GraphNodeType.DATABASE
        if requirement_type == RequirementType.DEPENDENCY:
            return GraphNodeType.DEPENDENCY
        if any(item in lowered for item in ("service", "router", "retriever", "client")):
            return GraphNodeType.SERVICE
        return GraphNodeType.COMPONENT

    @staticmethod
    def _predicate_relationship(predicate_type: str) -> GraphRelationshipType:
        value = predicate_type.upper()
        if "CALL" in value or "EXECUTION_PATH" in value:
            return GraphRelationshipType.CALLS
        if "TEST" in value:
            return GraphRelationshipType.TESTED_BY
        if "USE" in value or "DEPEND" in value:
            return GraphRelationshipType.USES
        return GraphRelationshipType.REQUIRES
