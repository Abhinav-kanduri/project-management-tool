from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.impact_analysis.enums import RetrievalMethod
from app.impact_analysis.schemas import StrictModel


class RetrievalCandidate(StrictModel):
    candidate_key: str
    method: RetrievalMethod
    snapshot_id: UUID
    file_id: UUID | None = None
    file_path: str | None = None
    symbol_id: UUID | None = None
    symbol: str | None = None
    chunk_id: UUID | None = None
    start_line: int | None = None
    end_line: int | None = None
    content: str | None = None
    content_sha256: str | None = None
    source_score: float = 0
    rank: int = Field(ge=1)
    fused_score: float = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
