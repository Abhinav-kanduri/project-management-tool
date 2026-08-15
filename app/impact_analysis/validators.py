from collections.abc import Collection, Iterable
from uuid import UUID

from app.impact_analysis.enums import (
    FindingStatus,
    PredicateResult,
    ReasonCode,
)


STATUS_REASON_CODES: dict[FindingStatus, frozenset[ReasonCode]] = {
    FindingStatus.PRESENT: frozenset({ReasonCode.IMPLEMENTED}),
    FindingStatus.PARTIAL: frozenset(
        {
            ReasonCode.PARTIAL_IMPLEMENTATION,
            ReasonCode.PARTIAL_EXECUTION_PATH,
            ReasonCode.CONTRADICTORY_EVIDENCE,
        }
    ),
    FindingStatus.MISSING: frozenset({ReasonCode.NO_IMPLEMENTATION_EVIDENCE}),
    FindingStatus.UNKNOWN: frozenset(
        {
            ReasonCode.INSUFFICIENT_STATIC_EVIDENCE,
            ReasonCode.RETRIEVAL_COVERAGE_INCOMPLETE,
            ReasonCode.UNSUPPORTED_LANGUAGE,
            ReasonCode.RUNTIME_VALIDATION_REQUIRED,
            ReasonCode.EXTERNAL_SYSTEM_EVIDENCE_REQUIRED,
        }
    ),
}


def validate_status_reason(status: FindingStatus, reason: ReasonCode) -> None:
    if reason not in STATUS_REASON_CODES[status]:
        raise ValueError(f"Reason code {reason} is not valid for status {status}")


def validate_evidence_references(
    referenced: Iterable[UUID], available: Collection[UUID]
) -> None:
    missing = set(referenced) - set(available)
    if missing:
        values = ", ".join(sorted(str(item) for item in missing))
        raise ValueError(f"Unknown evidence IDs: {values}")


def classify_predicates(
    results: Iterable[PredicateResult],
    *,
    coverage_sufficient: bool,
) -> FindingStatus:
    values = tuple(results)
    if not values or not coverage_sufficient or PredicateResult.UNKNOWN in values:
        return FindingStatus.UNKNOWN
    proven = values.count(PredicateResult.PROVEN)
    if proven == len(values):
        return FindingStatus.PRESENT
    if proven > 0:
        return FindingStatus.PARTIAL
    if all(
        value in {PredicateResult.NOT_PROVEN, PredicateResult.CONTRADICTED}
        for value in values
    ):
        return FindingStatus.MISSING
    return FindingStatus.UNKNOWN
