import re
from uuid import UUID

from app.impact_analysis.enums import RetrievalMethod
from app.impact_analysis.repositories.source_index import SourceIndexRepository
from app.impact_analysis.retrieval.models import RetrievalCandidate


class StructuredRetriever:
    def __init__(self, repository: SourceIndexRepository | None = None) -> None:
        self.repository = repository or SourceIndexRepository()

    def search(self, *, snapshot_id: UUID, query: str, limit: int = 30):
        terms = [item for item in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]+", query) if len(item) > 2]
        rows = self.repository.structured_search(
            snapshot_id=snapshot_id, terms=terms, limit=limit
        )
        return [self._candidate(row, index) for index, row in enumerate(rows, start=1)]

    @staticmethod
    def _candidate(row, rank):
        return RetrievalCandidate(
            candidate_key=f"chunk:{row['chunk_id']}",
            method=RetrievalMethod.STRUCTURED_SYMBOL,
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
            source_score=max(0, 1 - (rank - 1) * 0.02),
            rank=rank,
        )
