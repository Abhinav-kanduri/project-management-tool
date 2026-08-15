from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from app.database import get_connection
from app.impact_analysis.domain import (
    AcceptanceCriterionRecord,
    FeatureRecord,
    ProjectRecord,
    RepositoryMappingRecord,
    RequirementPackage,
    UserStoryRecord,
)
from app.impact_analysis.enums import ScopeType


class ScopeNotFoundError(LookupError):
    pass


class ScopeValidationError(ValueError):
    pass


class ScopeAccessDeniedError(PermissionError):
    pass


class ProjectContextRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def load(
        self,
        *,
        actor: str,
        product_space_id: UUID,
        project_id: UUID,
        release_id: UUID | None,
        scope_type: ScopeType,
        scope_id: UUID,
        project_repository_id: UUID,
    ) -> RequirementPackage:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            project = self._project(cursor, product_space_id, project_id)
            self._authorize(cursor, actor, project_id)
            repository = self._repository(cursor, project_id, project_repository_id)
            if scope_type == ScopeType.FEATURE:
                feature = self._feature(cursor, project_id, scope_id)
                story = None
                related = self._stories(cursor, project_id, feature.id)
            else:
                story = self._story(cursor, project_id, scope_id)
                feature = self._feature(cursor, project_id, story.feature_id)
                related = []
            if release_id is not None and feature.release_id != release_id:
                raise ScopeValidationError(
                    "The selected scope does not belong to the requested Release."
                )
            criteria = self._criteria(
                cursor,
                project_id,
                feature.id,
                story.id if story else None,
                include_feature=scope_type == ScopeType.FEATURE,
            )
        return RequirementPackage(
            project=project,
            scope_type=scope_type,
            scope_id=scope_id,
            release_id=release_id,
            feature=feature,
            user_story=story,
            acceptance_criteria=criteria,
            related_user_stories=related,
            repository=repository,
        )

    @staticmethod
    def _project(cursor, product_space_id: UUID, project_id: UUID) -> ProjectRecord:
        cursor.execute(
            """
            select p.organization_id, p.product_space_id, p.id project_id,
                   p.project_key, p.name project_name,
                   p.description project_description
            from projects p
            join product_spaces ps on ps.id=p.product_space_id
            where p.id=%s and p.product_space_id=%s
              and p.archived_at is null and ps.archived_at is null
            """,
            (project_id, product_space_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ScopeNotFoundError(
                "The selected Project was not found in the Product Space."
            )
        return ProjectRecord.model_validate(row)

    @staticmethod
    def _authorize(cursor, actor: str, project_id: UUID) -> None:
        try:
            actor_id = UUID(actor)
        except ValueError:
            # Preserve the current local-development actor convention until JWT
            # middleware provides a verified UUID subject.
            return
        cursor.execute(
            "select 1 from project_members where project_id=%s and user_id=%s",
            (project_id, actor_id),
        )
        if not cursor.fetchone():
            raise ScopeAccessDeniedError("Actor is not a member of the Project.")

    @staticmethod
    def _feature(cursor, project_id: UUID, feature_id: UUID) -> FeatureRecord:
        cursor.execute(
            """
            select id, feature_key, title, description, problem_statement,
                   business_value, functional_requirements,
                   non_functional_requirements, dependencies, risks, assumptions,
                   status, priority, release_id
            from features
            where id=%s and project_id=%s and archived_at is null
            """,
            (feature_id, project_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ScopeNotFoundError("Feature was not found in the Project.")
        return FeatureRecord.model_validate(row)

    @staticmethod
    def _story(cursor, project_id: UUID, story_id: UUID) -> UserStoryRecord:
        cursor.execute(
            """
            select id, feature_id, story_key, title, story_text, status,
                   priority, story_points, release_id, sprint_id
            from user_stories
            where id=%s and project_id=%s and archived_at is null
            """,
            (story_id, project_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ScopeNotFoundError("User Story was not found in the Project.")
        return UserStoryRecord.model_validate(row)

    @staticmethod
    def _stories(cursor, project_id: UUID, feature_id: UUID) -> list[UserStoryRecord]:
        cursor.execute(
            """
            select id, feature_id, story_key, title, story_text, status,
                   priority, story_points, release_id, sprint_id
            from user_stories
            where project_id=%s and feature_id=%s and archived_at is null
            order by story_key
            """,
            (project_id, feature_id),
        )
        return [UserStoryRecord.model_validate(row) for row in cursor.fetchall()]

    @staticmethod
    def _criteria(
        cursor,
        project_id: UUID,
        feature_id: UUID,
        story_id: UUID | None,
        *,
        include_feature: bool,
    ) -> list[AcceptanceCriterionRecord]:
        if story_id:
            clause = "user_story_id=%s"
            parameters: tuple[Any, ...] = (project_id, story_id)
        elif include_feature:
            clause = "feature_id=%s and user_story_id is null"
            parameters = (project_id, feature_id)
        else:
            return []
        cursor.execute(
            f"""
            select id, feature_id, user_story_id, given_text given,
                   when_text "when", then_text "then", criteria_order "order"
            from acceptance_criteria
            where project_id=%s and {clause}
            order by criteria_order, id
            """,
            parameters,
        )
        return [AcceptanceCriterionRecord.model_validate(row) for row in cursor.fetchall()]

    @staticmethod
    def _repository(
        cursor, project_id: UUID, project_repository_id: UUID
    ) -> RepositoryMappingRecord:
        cursor.execute(
            """
            select link.id project_repository_id, r.id repository_id,
                   r.github_repository_id, r.full_name, r.html_url repository_url,
                   r.default_branch, r.private, r.archived
            from project_github_repositories link
            join github_repositories r on r.id=link.repository_id
            where link.id=%s and link.project_id=%s
            """,
            (project_repository_id, project_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ScopeValidationError(
                "The selected GitHub repository is not linked to this Project."
            )
        if row["archived"]:
            raise ScopeValidationError("The selected GitHub repository is archived.")
        return RepositoryMappingRecord.model_validate(row)
