from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.impact_analysis.remediation.models import ChangeProposal, ValidationCheck


RESTRICTED_PATHS = (
    ".env",
    ".git/",
    ".github/workflows/",
)
DESTRUCTIVE_SQL = re.compile(r"\b(drop\s+(database|schema)|truncate\s+table)\b", re.I)


class PatchPolicy:
    def validate(self, proposal: ChangeProposal) -> list[ValidationCheck]:
        checks = [self._paths(proposal), self._format(proposal), self._policy(proposal)]
        checks.extend(
            [
                ValidationCheck(
                    check_type="LINT",
                    status="SKIPPED",
                    log_excerpt="Requires an isolated repository workspace adapter.",
                ),
                ValidationCheck(
                    check_type="UNIT_TEST",
                    status="SKIPPED",
                    log_excerpt="Requires an isolated repository workspace adapter.",
                ),
                ValidationCheck(
                    check_type="SECURITY",
                    status="SKIPPED",
                    log_excerpt="Requires an isolated repository workspace adapter.",
                ),
            ]
        )
        return checks

    def _paths(self, proposal: ChangeProposal) -> ValidationCheck:
        errors = []
        for item in proposal.proposed_files:
            normalized = item.path.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts:
                errors.append(f"Unsafe path: {item.path}")
            if any(normalized == prefix or normalized.startswith(prefix) for prefix in RESTRICTED_PATHS):
                errors.append(f"Restricted path: {item.path}")
        return ValidationCheck(
            check_type="PATH_SAFETY",
            status="FAILED" if errors else "PASSED",
            log_excerpt="; ".join(errors) if errors else "All proposed paths are repository-relative.",
        )

    @staticmethod
    def _format(proposal: ChangeProposal) -> ValidationCheck:
        patch_paths = set(re.findall(r"^diff --git a/(.+?) b/(.+?)$", proposal.patch, re.M))
        flattened = {path for pair in patch_paths for path in pair}
        missing = [item.path for item in proposal.proposed_files if item.path not in flattened]
        return ValidationCheck(
            check_type="FORMAT",
            status="FAILED" if missing else "PASSED",
            log_excerpt=(
                "Files absent from diff headers: " + ", ".join(missing)
                if missing
                else "Unified diff headers match proposed files."
            ),
        )

    @staticmethod
    def _policy(proposal: ChangeProposal) -> ValidationCheck:
        errors = []
        if "GITHUB_TOKEN=" in proposal.patch or "OPENAI_API_KEY=" in proposal.patch:
            errors.append("Patch appears to contain a secret assignment")
        if DESTRUCTIVE_SQL.search(proposal.patch):
            errors.append("Patch contains destructive SQL")
        return ValidationCheck(
            check_type="POLICY",
            status="FAILED" if errors else "PASSED",
            log_excerpt="; ".join(errors) if errors else "Static remediation policy passed.",
        )
