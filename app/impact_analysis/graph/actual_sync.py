from uuid import UUID

from app.impact_analysis.graph.actual_builder import ActualGraphBuilder
from app.impact_analysis.graph.repository import ImpactGraphRepository
from app.impact_analysis.repositories.source_index import SourceIndexRepository


class ActualGraphSynchronizer:
    def __init__(
        self,
        *,
        source_repository: SourceIndexRepository | None = None,
        graph_repository: ImpactGraphRepository | None = None,
    ) -> None:
        self.source_repository = source_repository or SourceIndexRepository()
        self.graph_repository = graph_repository or ImpactGraphRepository()

    def sync(
        self,
        *,
        run_id: UUID,
        snapshot_id: UUID,
        repository_name: str,
        project_id: UUID,
    ):
        rows = self.source_repository.graph_rows(snapshot_id)
        batch = ActualGraphBuilder().build(
            run_id=run_id,
            snapshot_id=snapshot_id,
            repository_name=repository_name,
            project_id=project_id,
            rows=rows,
        )
        self.graph_repository.upsert(batch, run_id=str(run_id))
        return batch
