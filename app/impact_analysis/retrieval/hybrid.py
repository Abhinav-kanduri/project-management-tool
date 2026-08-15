from __future__ import annotations

from collections import defaultdict

from app.impact_analysis.retrieval.models import RetrievalCandidate


class HybridRetriever:
    def __init__(self, *, rrf_constant: int = 60) -> None:
        if rrf_constant < 1:
            raise ValueError("RRF constant must be positive")
        self.rrf_constant = rrf_constant

    def fuse(
        self,
        result_sets: list[list[RetrievalCandidate]],
        *,
        limit: int = 30,
    ) -> list[RetrievalCandidate]:
        scores: dict[str, float] = defaultdict(float)
        candidates: dict[str, RetrievalCandidate] = {}
        methods: dict[str, set[str]] = defaultdict(set)
        for result_set in result_sets:
            for candidate in result_set:
                scores[candidate.candidate_key] += 1 / (
                    self.rrf_constant + candidate.rank
                )
                candidates.setdefault(candidate.candidate_key, candidate)
                methods[candidate.candidate_key].add(candidate.method.value)
        ordered = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
        return [
            candidates[key].model_copy(
                update={
                    "rank": rank,
                    "fused_score": scores[key],
                    "metadata": {
                        **candidates[key].metadata,
                        "retrieval_methods": sorted(methods[key]),
                    },
                }
            )
            for rank, key in enumerate(ordered, start=1)
        ]
