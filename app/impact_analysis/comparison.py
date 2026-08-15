from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from app.impact_analysis.context import AnalysisContext
from app.impact_analysis.enums import (
    EvidenceDirection,
    FindingStatus,
    ImpactCategory,
    PredicateResult,
    ReasonCode,
    RequirementApplicability,
    RequirementType,
)
from app.impact_analysis.schemas import (
    EvidenceRecord,
    ImpactStatement,
    LLMComparisonCandidate,
)


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "for",
    "from", "has", "in", "is", "it", "must", "of", "on", "or", "should",
    "that", "the", "this", "to", "use", "using", "with",
}


@dataclass(frozen=True)
class ComparisonResult:
    candidate: LLMComparisonCandidate
    evidence: tuple[EvidenceRecord, ...]
    predicate_results: tuple[dict, ...]


class DeterministicComparator:
    """Evidence-first comparison used until an explicitly approved model adapter exists."""

    def compare(
        self,
        *,
        context: AnalysisContext,
        evidence: list[EvidenceRecord],
    ) -> ComparisonResult:
        requirement = context.requirement
        if requirement.requirement_id is None:
            raise ValueError("Persisted requirement ID is required for comparison")
        if requirement.applicability == RequirementApplicability.RUNTIME_EVIDENCE_REQUIRED:
            return self._unknown(
                requirement.requirement_id,
                evidence,
                ReasonCode.RUNTIME_VALIDATION_REQUIRED,
                "Runtime measurements are required; static repository evidence cannot prove this requirement.",
            )
        if requirement.applicability == RequirementApplicability.EXTERNAL_EVIDENCE_REQUIRED:
            return self._unknown(
                requirement.requirement_id,
                evidence,
                ReasonCode.EXTERNAL_SYSTEM_EVIDENCE_REQUIRED,
                "Evidence from an external system is required to verify this requirement.",
            )

        corpus = " ".join(
            " ".join(
                part for part in (item.file_path, item.symbol, item.excerpt) if part
            )
            for item in evidence
        ).casefold()
        predicate_results = []
        ratios = []
        for predicate in requirement.expected_predicates:
            tokens = self._tokens(" ".join(filter(None, (predicate.subject, predicate.object))))
            ratio = 0 if not tokens else sum(token in corpus for token in tokens) / len(tokens)
            ratios.append(ratio)
            if ratio >= 0.65:
                result = PredicateResult.PROVEN
            elif ratio > 0:
                result = PredicateResult.NOT_PROVEN
            else:
                result = PredicateResult.NOT_PROVEN
            predicate_results.append(
                {
                    "predicate_id": predicate.predicate_id,
                    "result": result.value,
                    "term_match_ratio": round(ratio, 4),
                }
            )

        best = max(ratios, default=0)
        coverage = context.retrieval_coverage_percent
        if best >= 0.65 and evidence:
            status = FindingStatus.PRESENT
            reason = ReasonCode.IMPLEMENTED
        elif best >= 0.2 and evidence:
            status = FindingStatus.PARTIAL
            reason = (
                ReasonCode.PARTIAL_EXECUTION_PATH
                if requirement.type == RequirementType.EXECUTION_PATH
                else ReasonCode.PARTIAL_IMPLEMENTATION
            )
        elif coverage >= 80:
            status = FindingStatus.MISSING
            reason = ReasonCode.NO_IMPLEMENTATION_EVIDENCE
        else:
            return self._unknown(
                requirement.requirement_id,
                evidence,
                ReasonCode.RETRIEVAL_COVERAGE_INCOMPLETE,
                f"Only {coverage:.1f}% of eligible repository files were indexed, so absence cannot be established.",
                predicate_results=predicate_results,
            )

        supporting = tuple(
            item.model_copy(update={"direction": EvidenceDirection.SUPPORTS})
            for item in evidence
        )
        evidence_ids = [item.evidence_id for item in supporting]
        present = (
            "Implementation evidence was found in the pinned repository snapshot."
            if status != FindingStatus.MISSING
            else ""
        )
        missing = {
            FindingStatus.PRESENT: "",
            FindingStatus.PARTIAL: "The retrieved implementation does not prove the complete required behavior or execution path.",
            FindingStatus.MISSING: "No sufficient implementation evidence was found in the indexed repository snapshot.",
        }[status]
        technical_reason = {
            FindingStatus.PRESENT: "The expected predicate is supported by file/function evidence at the pinned commit.",
            FindingStatus.PARTIAL: "Relevant source exists, but token and path evidence supports only part of the expected predicate.",
            FindingStatus.MISSING: f"No matching source, test, configuration, dependency, or migration evidence was found with {coverage:.1f}% repository coverage.",
        }[status]
        explanation = {
            FindingStatus.PRESENT: "The repository contains evidence for this requirement.",
            FindingStatus.PARTIAL: "Part of the requested capability appears to exist, but the complete behavior is not established.",
            FindingStatus.MISSING: "The analyzed repository does not contain enough evidence that this requirement has been implemented.",
        }[status]
        recommendation = {
            FindingStatus.PRESENT: "Retain the cited implementation and its tests during future changes.",
            FindingStatus.PARTIAL: "Review the cited files, complete the missing execution path, and add focused tests.",
            FindingStatus.MISSING: "Implement the requirement using existing repository patterns and add tests before release.",
        }[status]
        impacts = []
        if status != FindingStatus.PRESENT:
            impacts.append(
                ImpactStatement(
                    category=self._impact_category(requirement.type),
                    summary="The requested capability may remain incomplete until the identified gap is resolved.",
                    conditional=True,
                    evidence_ids=evidence_ids,
                )
            )
        confidence = {
            FindingStatus.PRESENT: min(0.98, 0.75 + best * 0.23),
            FindingStatus.PARTIAL: min(0.9, 0.6 + best * 0.4),
            FindingStatus.MISSING: min(0.95, 0.5 + coverage / 200),
        }[status]
        candidate = LLMComparisonCandidate(
            requirement_id=requirement.requirement_id,
            candidate_status=status,
            confidence=confidence,
            present_summary=present,
            missing_summary=missing,
            reason_code=reason,
            technical_reason=technical_reason,
            explanation=explanation,
            impacts=impacts,
            recommendation=recommendation,
            evidence_ids=evidence_ids,
        )
        return ComparisonResult(candidate, supporting, tuple(predicate_results))

    def _unknown(
        self,
        requirement_id: UUID,
        evidence: list[EvidenceRecord],
        reason: ReasonCode,
        technical_reason: str,
        *,
        predicate_results: list[dict] | None = None,
    ) -> ComparisonResult:
        contextual = tuple(
            item.model_copy(update={"direction": EvidenceDirection.CONTEXT})
            for item in evidence
        )
        candidate = LLMComparisonCandidate(
            requirement_id=requirement_id,
            candidate_status=FindingStatus.UNKNOWN,
            confidence=0.5,
            present_summary="",
            missing_summary="Static analysis cannot determine whether this requirement is complete.",
            reason_code=reason,
            technical_reason=technical_reason,
            explanation="Additional runtime, external, or repository coverage evidence is needed.",
            impacts=[],
            recommendation="Collect the required evidence and re-run the analysis.",
            evidence_ids=[item.evidence_id for item in contextual],
        )
        return ComparisonResult(candidate, contextual, tuple(predicate_results or ()))

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z][a-z0-9_]{2,}", value.casefold())
            if token not in STOP_WORDS
        }

    @staticmethod
    def _impact_category(requirement_type: RequirementType) -> ImpactCategory:
        return {
            RequirementType.TEST_COVERAGE: ImpactCategory.TESTING,
            RequirementType.SECURITY: ImpactCategory.SECURITY,
            RequirementType.DATA_PERSISTENCE: ImpactCategory.DATA,
            RequirementType.DATABASE_CHANGE: ImpactCategory.DATA,
            RequirementType.DEPENDENCY: ImpactCategory.DEPENDENCY,
            RequirementType.CONFIGURATION: ImpactCategory.OPERATIONAL,
            RequirementType.API_CONTRACT: ImpactCategory.INTEGRATION,
            RequirementType.NON_FUNCTIONAL: ImpactCategory.PERFORMANCE,
        }.get(requirement_type, ImpactCategory.FUNCTIONAL)
