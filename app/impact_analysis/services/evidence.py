from __future__ import annotations

from uuid import UUID, uuid5

from app.impact_analysis.enums import (
    EvidenceDirection,
    EvidenceType,
    RetrievalMethod,
)
from app.impact_analysis.retrieval.models import RetrievalCandidate
from app.impact_analysis.schemas import EvidenceRecord


EVIDENCE_NAMESPACE = UUID("d60c113f-327a-4207-99de-2c88fd88f418")


class EvidenceMaterializer:
    def materialize(
        self,
        *,
        run_id: UUID,
        requirement_id: UUID,
        repository: str,
        commit_sha: str,
        candidates: list[RetrievalCandidate],
    ) -> list[EvidenceRecord]:
        evidence: list[EvidenceRecord] = []
        for rank, candidate in enumerate(candidates, start=1):
            evidence_id = uuid5(
                EVIDENCE_NAMESPACE,
                f"{run_id}:{requirement_id}:{candidate.candidate_key}",
            )
            evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    requirement_id=requirement_id,
                    type=self._type(candidate.file_path),
                    direction=EvidenceDirection.CONTEXT,
                    retrieval_method=RetrievalMethod.HYBRID,
                    repository=repository,
                    commit_sha=commit_sha,
                    file_path=candidate.file_path,
                    symbol=candidate.symbol,
                    start_line=candidate.start_line,
                    end_line=candidate.end_line,
                    description=self._description(candidate),
                    excerpt=candidate.content,
                    rank=rank,
                    score=candidate.fused_score or candidate.source_score,
                    metadata={
                        **candidate.metadata,
                        "candidate_key": candidate.candidate_key,
                        "file_id": str(candidate.file_id) if candidate.file_id else None,
                        "symbol_id": str(candidate.symbol_id) if candidate.symbol_id else None,
                        "chunk_id": str(candidate.chunk_id) if candidate.chunk_id else None,
                        "content_sha256": candidate.content_sha256,
                    },
                )
            )
        return evidence

    @staticmethod
    def _type(path: str | None) -> EvidenceType:
        value = (path or "").casefold()
        name = value.rsplit("/", 1)[-1]
        if "test" in name or "/tests/" in f"/{value}":
            return EvidenceType.TEST
        if value.endswith(".sql"):
            return EvidenceType.DATABASE_MIGRATION
        if name in {"requirements.txt", "pyproject.toml", "package.json", "poetry.lock"}:
            return EvidenceType.DEPENDENCY
        if value.endswith((".yaml", ".yml", ".toml", ".ini", ".env")):
            return EvidenceType.CONFIGURATION
        return EvidenceType.SOURCE_CODE

    @staticmethod
    def _description(candidate: RetrievalCandidate) -> str:
        location = candidate.file_path or "repository source"
        if candidate.symbol:
            location += f"::{candidate.symbol}"
        if candidate.start_line is not None:
            location += f" lines {candidate.start_line}-{candidate.end_line}"
        return f"Relevant implementation evidence retrieved from {location}."
