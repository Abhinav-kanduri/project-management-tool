from app.impact_analysis.domain import DesignEvidencePackage, RequirementPackage
from app.impact_analysis.repositories.design_documents import DesignDocumentRepository


class DesignContextService:
    def __init__(self, repository: DesignDocumentRepository | None = None) -> None:
        self.repository = repository or DesignDocumentRepository()

    def load(self, package: RequirementPackage, *, limit: int = 12) -> DesignEvidencePackage:
        terms = [package.feature.title]
        terms.extend(package.feature.functional_requirements)
        if package.user_story:
            terms.extend([package.user_story.title, package.user_story.story_text or ""])
        query = " ".join(item for item in terms if item)
        return self.repository.search(
            project_id=package.project.project_id,
            query=query,
            limit=limit,
        )
