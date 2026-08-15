from collections.abc import Callable
from uuid import UUID

from app.impact_analysis.enums import RetrievalMethod
from app.impact_analysis.repositories.source_index import SourceIndexRepository
from app.impact_analysis.retrieval.models import RetrievalCandidate


class VectorRetriever:
    """Vector retrieval with an explicitly injected embedding provider."""

    def __init__(
        self,
        *,
        embedding_provider: Callable[[str], list[float]] | None = None,
        repository: SourceIndexRepository | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.repository = repository or SourceIndexRepository()

    def search(self, *, snapshot_id: UUID, query: str, limit: int = 30):
        if self.embedding_provider is None:
            return []
        vector = self.embedding_provider(query)
        rows = self.repository.vector_search(
            snapshot_id=snapshot_id, query_vector=vector, limit=limit
        )
        return [
            RetrievalCandidate(
                candidate_key=f"chunk:{row['chunk_id']}",
                method=RetrievalMethod.VECTOR,
                snapshot_id=row["snapshot_id"],
                file_id=row["file_id"],
                file_path=row["path"],
                symbol_id=row.get("symbol_id"),
                symbol=row.get("qualified_name"),
                chunk_id=row["chunk_id"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                content=row["content"],
                content_sha256=row["content_sha256"],
                source_score=float(row.get("score") or 0),
                rank=index,
            )
            for index, row in enumerate(rows, start=1)
        ]
