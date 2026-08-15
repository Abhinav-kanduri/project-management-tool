from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from app.impact_analysis.domain import (
    DesignEvidencePackage,
    RequirementCandidate,
    RequirementCandidateSet,
    RequirementPackage,
)
from app.impact_analysis.enums import RequirementApplicability, RequirementType
from app.impact_analysis.schemas import (
    AtomicRequirement,
    ExpectedPredicate,
    RequirementProvenance,
)


class RequirementValidationError(ValueError):
    pass


CandidateGenerator = Callable[
    [RequirementPackage, DesignEvidencePackage], RequirementCandidateSet
]

PREDICATE_VALUE_MAX_LENGTH = 500


class RequirementDecomposer:
    """Create atomic requirements without an implicit external data transfer.

    The default generator is deterministic. A structured model adapter can be
    injected later, but the caller must make that policy decision explicitly.
    All generated candidates pass through the same deterministic validators.
    """

    def __init__(self, generator: CandidateGenerator | None = None) -> None:
        self._generator = generator or self._deterministic_candidates

    def decompose(
        self,
        package: RequirementPackage,
        design: DesignEvidencePackage,
    ) -> list[AtomicRequirement]:
        valid_references = self._valid_references(package, design)
        candidates = self._generator(package, design)
        return self.validate_candidates(candidates, valid_references)

    @staticmethod
    def validate_candidates(
        candidates: RequirementCandidateSet,
        valid_references: set[str],
    ) -> list[AtomicRequirement]:
        seen: set[str] = set()
        validated = []
        weight = 1 / len(candidates.requirements)
        for index, candidate in enumerate(candidates.requirements, start=1):
            text = " ".join(candidate.text.split()).strip().rstrip(";")
            normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
            if normalized in seen:
                raise RequirementValidationError(f"Duplicate requirement: {text}")
            seen.add(normalized)
            if ";" in text or len(re.findall(r"\bmust\b", text, re.I)) > 1:
                raise RequirementValidationError(
                    f"Requirement is compound and must be split: {text}"
                )
            unknown = set(candidate.source_references) - valid_references
            if unknown:
                raise RequirementValidationError(
                    "Requirement references unknown sources: "
                    + ", ".join(sorted(unknown))
                )
            predicates = []
            for predicate_index, raw in enumerate(candidate.predicates, start=1):
                allowed = {"predicate_type", "subject", "object", "mandatory"}
                if set(raw) - allowed:
                    raise RequirementValidationError(
                        f"Predicate contains unsupported fields: {sorted(set(raw)-allowed)}"
                    )
                if not raw.get("predicate_type") or not raw.get("subject"):
                    raise RequirementValidationError("Predicate type and subject are required")
                predicates.append(
                    ExpectedPredicate(
                        predicate_id=f"PRED-{index:03d}-{predicate_index:02d}",
                        predicate_type=str(raw["predicate_type"]).upper(),
                        subject=RequirementDecomposer._bounded_predicate_value(
                            raw["subject"]
                        ),
                        object=(
                            RequirementDecomposer._bounded_predicate_value(raw["object"])
                            if raw.get("object")
                            else None
                        ),
                        mandatory=bool(raw.get("mandatory", True)),
                    )
                )
            validated.append(
                AtomicRequirement(
                    requirement_key=f"REQ-{index:03d}",
                    text=text,
                    type=candidate.type,
                    applicability=candidate.applicability,
                    weight=weight,
                    provenance=[
                        RequirementProvenance(
                            source_type=reference.split(":", 1)[0],
                            source_id=reference,
                            source_locator={"reference": reference},
                        )
                        for reference in candidate.source_references
                    ],
                    expected_predicates=predicates,
                )
            )
        return validated

    @staticmethod
    def _bounded_predicate_value(value: object) -> str:
        """Normalize predicate search text without discarding requirement detail."""
        normalized = " ".join(str(value).split()).strip()
        if len(normalized) <= PREDICATE_VALUE_MAX_LENGTH:
            return normalized

        prefix = normalized[: PREDICATE_VALUE_MAX_LENGTH - 3]
        if " " in prefix:
            prefix = prefix.rsplit(" ", 1)[0]
        return f"{prefix.rstrip()}..."

    @staticmethod
    def _valid_references(
        package: RequirementPackage, design: DesignEvidencePackage
    ) -> set[str]:
        values = {f"FEATURE:{package.feature.id}"}
        if package.user_story:
            values.add(f"USER_STORY:{package.user_story.id}")
        values.update(f"ACCEPTANCE_CRITERION:{item.id}" for item in package.acceptance_criteria)
        values.update(
            f"DESIGN:{item.document_id}:{item.chunk_id}" for item in design.items
        )
        return values

    @classmethod
    def _deterministic_candidates(
        cls,
        package: RequirementPackage,
        design: DesignEvidencePackage,
    ) -> RequirementCandidateSet:
        inputs: list[tuple[str, str]] = []
        feature_ref = f"FEATURE:{package.feature.id}"
        inputs.extend((value, feature_ref) for value in package.feature.functional_requirements)
        inputs.extend(
            (value, feature_ref) for value in package.feature.non_functional_requirements
        )
        if package.user_story:
            story_ref = f"USER_STORY:{package.user_story.id}"
            inputs.extend(
                (value, story_ref)
                for value in (package.user_story.title, package.user_story.story_text or "")
                if value
            )
        for criterion in package.acceptance_criteria:
            statement = " ".join(
                value
                for value in (criterion.given, criterion.when, criterion.then)
                if value
            )
            if statement:
                inputs.append((statement, f"ACCEPTANCE_CRITERION:{criterion.id}"))
        if not inputs:
            inputs.append((package.feature.title, feature_ref))

        candidates: list[RequirementCandidate] = []
        for text, reference in inputs:
            for atomic in cls._split_atomic(text):
                requirement_type, applicability = cls._classify(atomic)
                candidates.append(
                    RequirementCandidate(
                        text=atomic,
                        type=requirement_type,
                        applicability=applicability,
                        source_references=[reference],
                        predicates=[
                            {
                                "predicate_type": cls._predicate_type(requirement_type),
                                "subject": atomic,
                                "mandatory": True,
                            }
                        ],
                    )
                )
        return RequirementCandidateSet(requirements=cls._deduplicate(candidates))

    @staticmethod
    def _split_atomic(text: str) -> list[str]:
        normalized = re.sub(r"^[\s\-*\d.)]+", "", " ".join(text.split())).strip()
        normalized = re.sub(r"(?<=[A-Za-z])(?=must\b)", " ", normalized, flags=re.I)
        sentence_parts = [
            item.strip()
            for item in re.split(r"[;\n]+|(?<=[.!?])\s+(?=[A-Z])", normalized)
            if len(item.strip()) >= 5
        ]
        atomic: list[str] = []
        for item in sentence_parts:
            atomic.extend(RequirementDecomposer._split_repeated_must(item))
        return [item for item in atomic if len(item) >= 5]

    @staticmethod
    def _split_repeated_must(text: str) -> list[str]:
        must_matches = list(re.finditer(r"\bmust\b", text, re.I))
        if len(must_matches) <= 1:
            return [text]

        subject = text[: must_matches[0].start()].strip()
        split_ranges: list[tuple[int, int]] = []
        previous_must = must_matches[0]
        for current_must in must_matches[1:]:
            conjunctions = list(
                re.finditer(
                    r"(?:,\s*)?\band\s+",
                    text[previous_must.end() : current_must.start()],
                    re.I,
                )
            )
            if conjunctions:
                split_ranges.append(
                    (
                        previous_must.end() + conjunctions[-1].start(),
                        previous_must.end() + conjunctions[-1].end(),
                    )
                )
            previous_must = current_must

        if not split_ranges:
            return [text]

        parts: list[str] = []
        start = 0
        for split_start, split_end in split_ranges:
            if part := text[start:split_start].strip(" ,"):
                parts.append(part)
            start = split_end
        if part := text[start:].strip(" ,"):
            parts.append(part)
        if len(parts) <= 1:
            return [text]

        result = [parts[0]]
        for part in parts[1:]:
            if subject and re.match(r"must\b", part, re.I):
                result.append(f"{subject} {part}")
            else:
                result.append(part)
        return result

    @staticmethod
    def _classify(text: str) -> tuple[RequirementType, RequirementApplicability]:
        value = text.casefold()
        if any(term in value for term in ("latency", "within ", "milliseconds", "throughput")):
            return RequirementType.NON_FUNCTIONAL, RequirementApplicability.RUNTIME_EVIDENCE_REQUIRED
        if any(term in value for term in ("secure", "authorization", "authentication", "encrypt")):
            return RequirementType.SECURITY, RequirementApplicability.STATICALLY_VERIFIABLE
        if any(term in value for term in ("test", "coverage", "pytest")):
            return RequirementType.TEST_COVERAGE, RequirementApplicability.STATICALLY_VERIFIABLE
        if any(term in value for term in ("persist", "database", "store", "migration")):
            return RequirementType.DATA_PERSISTENCE, RequirementApplicability.STATICALLY_VERIFIABLE
        if any(term in value for term in ("endpoint", " api", "http ", "request", "response")):
            return RequirementType.API_CONTRACT, RequirementApplicability.STATICALLY_VERIFIABLE
        if any(term in value for term in ("config", "environment variable", "setting")):
            return RequirementType.CONFIGURATION, RequirementApplicability.STATICALLY_VERIFIABLE
        if any(term in value for term in ("depend", "package", "library")):
            return RequirementType.DEPENDENCY, RequirementApplicability.STATICALLY_VERIFIABLE
        if any(term in value for term in ("call", "invoke", "use ", "integrat", "flow")):
            return RequirementType.EXECUTION_PATH, RequirementApplicability.STATICALLY_VERIFIABLE
        return RequirementType.COMPONENT_EXISTENCE, RequirementApplicability.STATICALLY_VERIFIABLE

    @staticmethod
    def _predicate_type(requirement_type: RequirementType) -> str:
        return {
            RequirementType.COMPONENT_EXISTENCE: "EXISTS",
            RequirementType.EXECUTION_PATH: "EXECUTION_PATH_EXISTS",
            RequirementType.API_CONTRACT: "API_EXISTS",
            RequirementType.DATA_PERSISTENCE: "PERSISTENCE_EXISTS",
            RequirementType.DATABASE_CHANGE: "MIGRATION_EXISTS",
            RequirementType.CONFIGURATION: "CONFIGURATION_EXISTS",
            RequirementType.DEPENDENCY: "DEPENDENCY_EXISTS",
            RequirementType.TEST_COVERAGE: "TEST_EXISTS",
            RequirementType.SECURITY: "SECURITY_CONTROL_EXISTS",
            RequirementType.NON_FUNCTIONAL: "RUNTIME_VALIDATION_REQUIRED",
            RequirementType.OTHER: "IMPLEMENTATION_EXISTS",
        }[requirement_type]

    @staticmethod
    def _deduplicate(
        candidates: Iterable[RequirementCandidate],
    ) -> list[RequirementCandidate]:
        result: list[RequirementCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = re.sub(r"[^a-z0-9]+", " ", candidate.text.casefold()).strip()
            if key not in seen:
                seen.add(key)
                result.append(candidate)
        return result
