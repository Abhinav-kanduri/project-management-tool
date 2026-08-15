from __future__ import annotations

from dataclasses import dataclass

from app.impact_analysis.enums import FindingStatus


COMPLETION = {
    FindingStatus.PRESENT: 1.0,
    FindingStatus.PARTIAL: 0.5,
    FindingStatus.MISSING: 0.0,
}


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    applicable_weight: float
    excluded_weight: float
    contributions: tuple[float | None, ...]


def calculate_score(items: list[tuple[FindingStatus, float]]) -> ScoreResult:
    applicable_weight = sum(weight for status, weight in items if status != FindingStatus.UNKNOWN)
    excluded_weight = sum(weight for status, weight in items if status == FindingStatus.UNKNOWN)
    contributions = tuple(
        None
        if status == FindingStatus.UNKNOWN
        else weight * COMPLETION[status] * 100
        for status, weight in items
    )
    if applicable_weight == 0:
        score = None
    else:
        numerator = sum(value or 0 for value in contributions)
        score = round(numerator / applicable_weight, 4)
    return ScoreResult(
        score=score,
        applicable_weight=applicable_weight,
        excluded_weight=excluded_weight,
        contributions=contributions,
    )
