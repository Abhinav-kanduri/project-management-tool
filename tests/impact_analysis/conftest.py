from uuid import uuid4

import pytest

from app.impact_analysis.domain import (
    AcceptanceCriterionRecord,
    FeatureRecord,
    ProjectRecord,
    RepositoryMappingRecord,
    RequirementPackage,
    UserStoryRecord,
)
from app.impact_analysis.enums import ScopeType


@pytest.fixture
def requirement_package() -> RequirementPackage:
    organization_id = uuid4()
    product_space_id = uuid4()
    project_id = uuid4()
    release_id = uuid4()
    feature_id = uuid4()
    story_id = uuid4()
    return RequirementPackage(
        project=ProjectRecord(
            organization_id=organization_id,
            product_space_id=product_space_id,
            project_id=project_id,
            project_key="CSA",
            project_name="Customer Support AI",
        ),
        scope_type=ScopeType.USER_STORY,
        scope_id=story_id,
        release_id=release_id,
        feature=FeatureRecord(
            id=feature_id,
            feature_key="CSA-F-001",
            title="Chat Orchestrator",
            description="Orchestrate support chat requests.",
            functional_requirements=[
                "Agent Router must invoke RAG retrieval",
                "RAG retrieval must use Redis caching",
            ],
            non_functional_requirements=[
                "System must respond within 500 milliseconds"
            ],
            status="BACKLOG",
            priority="HIGH",
            release_id=release_id,
        ),
        user_story=UserStoryRecord(
            id=story_id,
            feature_id=feature_id,
            story_key="CSA-102",
            title="Agent Router and RAG Retrieval",
            story_text="As a support user, I want routed retrieval for grounded answers",
            status="BACKLOG",
            priority="HIGH",
            story_points=8,
            release_id=release_id,
        ),
        acceptance_criteria=[
            AcceptanceCriterionRecord(
                id=uuid4(),
                feature_id=feature_id,
                user_story_id=story_id,
                given="A support request",
                when="The router processes it",
                then="The RAG retriever is invoked",
                order=1,
            )
        ],
        repository=RepositoryMappingRecord(
            project_repository_id=uuid4(),
            repository_id=uuid4(),
            github_repository_id=123,
            full_name="example/customer-support",
            repository_url="https://github.com/example/customer-support",
            default_branch="main",
            private=True,
            archived=False,
        ),
    )
