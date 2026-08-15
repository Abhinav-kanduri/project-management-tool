from __future__ import annotations

from typing import Any

from pydantic import Field

from app.impact_analysis.domain import DesignEvidencePackage, RequirementPackage
from app.impact_analysis.retrieval.models import RetrievalCandidate
from app.impact_analysis.schemas import AtomicRequirement, StrictModel


class SourceContext(StrictModel):
    candidate_key: str
    file_path: str | None = None
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    excerpt: str
    retrieval_methods: list[str] = Field(default_factory=list)
    score: float = 0


class AnalysisContext(StrictModel):
    requirement: AtomicRequirement
    project: dict[str, Any]
    scope: dict[str, Any]
    design_evidence: list[dict[str, Any]]
    source_evidence: list[SourceContext]
    repository: dict[str, Any]
    retrieval_coverage_percent: float = Field(ge=0, le=100)
    truncated: bool = False


class ContextBuilder:
    def __init__(
        self,
        *,
        max_candidates: int = 12,
        max_excerpt_chars: int = 4_000,
        max_total_chars: int = 24_000,
    ) -> None:
        self.max_candidates = max_candidates
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars

    def build(
        self,
        *,
        requirement: AtomicRequirement,
        package: RequirementPackage,
        design: DesignEvidencePackage,
        candidates: list[RetrievalCandidate],
        snapshot: dict[str, Any],
    ) -> AnalysisContext:
        remaining = self.max_total_chars
        design_items = []
        design_truncated = False
        for item in design.items[:6]:
            data = item.model_dump(mode="json")
            text = data.get("text", "")
            data["text"] = text[: min(2_000, remaining)]
            remaining -= len(data["text"])
            design_items.append(data)
            if len(data["text"]) < len(text) or remaining <= 0:
                design_truncated = len(data["text"]) < len(text)
                break
        selected: list[SourceContext] = []
        truncated = (
            design_truncated
            or len(candidates) > self.max_candidates
            or len(design.items) > len(design_items)
        )
        if remaining <= 0 and candidates:
            truncated = True
        for candidate in candidates[: self.max_candidates]:
            if remaining <= 0:
                break
            content = candidate.content or ""
            excerpt = content[: min(self.max_excerpt_chars, remaining)]
            if not excerpt:
                continue
            if len(excerpt) < len(content):
                truncated = True
            selected.append(
                SourceContext(
                    candidate_key=candidate.candidate_key,
                    file_path=candidate.file_path,
                    symbol=candidate.symbol,
                    start_line=candidate.start_line,
                    end_line=candidate.end_line,
                    excerpt=excerpt,
                    retrieval_methods=candidate.metadata.get(
                        "retrieval_methods", [candidate.method.value]
                    ),
                    score=candidate.fused_score or candidate.source_score,
                )
            )
            remaining -= len(excerpt)
            if remaining <= 0:
                truncated = True
                break
        scope = package.user_story or package.feature
        return AnalysisContext(
            requirement=requirement,
            project={
                "id": str(package.project.project_id),
                "key": package.project.project_key,
                "name": package.project.project_name,
            },
            scope={
                "type": package.scope_type.value,
                "id": str(package.scope_id),
                "key": scope.story_key if package.user_story else scope.feature_key,
                "title": scope.title,
            },
            design_evidence=design_items,
            source_evidence=selected,
            repository={
                "full_name": package.repository.full_name,
                "branch": snapshot["branch"],
                "commit_sha": snapshot["commit_sha"],
                "snapshot_id": str(snapshot["id"]),
            },
            retrieval_coverage_percent=float(snapshot.get("coverage_percent") or 0),
            truncated=truncated,
        )
