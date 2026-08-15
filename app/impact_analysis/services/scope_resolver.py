from uuid import UUID

from app.impact_analysis.domain import RequirementPackage
from app.impact_analysis.enums import ScopeType
from app.impact_analysis.repositories.project_context import ProjectContextRepository


class ScopeResolver:
    def __init__(self, repository: ProjectContextRepository | None = None) -> None:
        self.repository = repository or ProjectContextRepository()

    def resolve(
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
        return self.repository.load(
            actor=actor,
            product_space_id=product_space_id,
            project_id=project_id,
            release_id=release_id,
            scope_type=scope_type,
            scope_id=scope_id,
            project_repository_id=project_repository_id,
        )
