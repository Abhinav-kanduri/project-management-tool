from uuid import UUID

from app.impact_analysis.enums import RetrievalMethod
from app.impact_analysis.graph.repository import ImpactGraphRepository


class GraphRetriever:
    def __init__(self, repository: ImpactGraphRepository | None = None) -> None:
        self.repository = repository or ImpactGraphRepository()

    def search(self, *, run_id: UUID) -> list[dict]:
        graph = self.repository.subgraph(run_id=str(run_id))
        return [
            {"method": RetrievalMethod.GRAPH, "rank": index, "path": edge}
            for index, edge in enumerate(graph["edges"], start=1)
        ]
