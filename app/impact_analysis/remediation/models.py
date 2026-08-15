from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field, field_validator

from app.impact_analysis.schemas import StrictModel


class ProposedFile(StrictModel):
    path: str = Field(min_length=1, max_length=1000)
    action: str = Field(pattern="^(ADD|MODIFY|DELETE)$")


class ChangeProposal(StrictModel):
    proposed_files: list[ProposedFile] = Field(min_length=1, max_length=100)
    patch: str = Field(min_length=1, max_length=1_000_000)
    explanation: str = Field(min_length=1, max_length=20_000)
    tests_proposed: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("patch")
    @classmethod
    def unified_diff_required(cls, value: str) -> str:
        if "diff --git a/" not in value or "--- " not in value or "+++ " not in value:
            raise ValueError("A git unified diff is required")
        return value


class CodeGenerationContext(StrictModel):
    finding: dict[str, Any]
    requirement: dict[str, Any]
    expected_predicates: list[dict[str, Any]]
    repository: dict[str, Any]
    evidence: list[dict[str, Any]]
    repository_conventions: dict[str, Any]
    constraints: list[str]


class ValidationCheck(StrictModel):
    check_type: str
    status: str
    command: str | None = None
    exit_code: int | None = None
    log_excerpt: str | None = None


class PullRequestResult(StrictModel):
    branch_name: str
    commit_sha: str
    pull_request_number: int = Field(gt=0)
    pull_request_url: str


class CodeGenerationProvider(Protocol):
    def generate(self, context: CodeGenerationContext) -> ChangeProposal: ...


class PullRequestPublisher(Protocol):
    async def publish(
        self, *, change: dict[str, Any], context: CodeGenerationContext
    ) -> PullRequestResult: ...
