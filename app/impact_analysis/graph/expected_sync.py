from uuid import UUID

from app.impact_analysis.graph.models import GraphBatch
from app.impact_analysis.graph.repository import ImpactGraphRepository


class ExpectedGraphSynchronizer:
    def __init__(self, repository: ImpactGraphRepository | None = None) -> None:
        self.repository = repository or ImpactGraphRepository()

    def sync(self, run_id: UUID, batch: GraphBatch) -> None:
        self.repository.upsert(batch, run_id=str(run_id))
