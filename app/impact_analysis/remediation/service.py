from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.impact_analysis.remediation.models import (
    ChangeProposal,
    CodeGenerationContext,
    CodeGenerationProvider,
    PullRequestPublisher,
    ValidationCheck,
)
from app.impact_analysis.remediation.policy import PatchPolicy
from app.impact_analysis.repositories.generated_changes import GeneratedChangeRepository


class ProviderNotConfiguredError(RuntimeError):
    pass


class WorkspaceValidator(Protocol):
    def validate(
        self, *, change: dict, context: CodeGenerationContext
    ) -> list[ValidationCheck]: ...


class RemediationService:
    def __init__(
        self,
        *,
        repository: GeneratedChangeRepository | None = None,
        generator: CodeGenerationProvider | None = None,
        workspace_validator: WorkspaceValidator | None = None,
        publisher: PullRequestPublisher | None = None,
    ) -> None:
        self.repository = repository or GeneratedChangeRepository()
        self.generator = generator
        self.workspace_validator = workspace_validator
        self.publisher = publisher
        self.policy = PatchPolicy()

    def request(self, *, finding_id: UUID, actor: UUID) -> dict:
        return self.repository.request(finding_id=finding_id, actor=actor)

    def get(self, *, change_id: UUID, actor: UUID) -> dict:
        return self.repository.get(change_id, actor=actor)

    def build_context(self, *, change_id: UUID, actor: UUID) -> CodeGenerationContext:
        row = self.repository.context(change_id, actor=actor)
        return CodeGenerationContext(
            finding={
                "id": str(row["finding_id"]),
                "status": row["finding_status"],
                "what_present": row["what_present"],
                "what_missing": row["what_missing"],
                "technical_reason": row["technical_reason"],
                "explanation": row["explanation"],
                "recommendation": row["recommendation"],
            },
            requirement={
                "id": str(row["requirement_id"]),
                "text": row["requirement_text"],
                "type": row["requirement_type"],
                "applicability": row["applicability"],
            },
            expected_predicates=row["expected_predicates"],
            repository={
                "full_name": row["repository_name"],
                "branch": row["branch"],
                "base_commit_sha": row["commit_sha"],
            },
            evidence=row["evidence"],
            repository_conventions={
                "source_of_truth": "Pinned repository evidence",
                "reuse_existing_patterns": True,
            },
            constraints=[
                "Do not modify the default branch directly.",
                "Keep every path repository-relative.",
                "Do not include credentials or secrets.",
                "Add or update focused tests.",
                "Return a git unified diff only.",
            ],
        )

    def generate(self, *, change_id: UUID, actor: UUID) -> dict:
        if self.generator is None:
            raise ProviderNotConfiguredError(
                "No code-generation provider is configured. Repository evidence was not transferred."
            )
        context = self.build_context(change_id=change_id, actor=actor)
        proposal = self.generator.generate(context)
        preflight = self.policy.validate(proposal)
        failed = [item for item in preflight[:3] if item.status != "PASSED"]
        if failed:
            self.repository.save_proposal(change_id, proposal=proposal, actor=actor)
            self.repository.save_validations(change_id, checks=preflight, actor=actor)
            return self.repository.get(change_id, actor=actor)
        return self.repository.save_proposal(change_id, proposal=proposal, actor=actor)

    def submit_proposal(
        self, *, change_id: UUID, actor: UUID, proposal: ChangeProposal
    ) -> dict:
        checks = self.policy.validate(proposal)
        row = self.repository.save_proposal(change_id, proposal=proposal, actor=actor)
        if any(item.status == "FAILED" for item in checks):
            self.repository.save_validations(change_id, checks=checks, actor=actor)
            return self.repository.get(change_id, actor=actor)
        return row

    def validate(self, *, change_id: UUID, actor: UUID) -> dict:
        if self.workspace_validator is None:
            raise ProviderNotConfiguredError(
                "No isolated workspace validator is configured; approval remains blocked."
            )
        change = self.repository.get(change_id, actor=actor)
        context = self.build_context(change_id=change_id, actor=actor)
        proposal = ChangeProposal(
            proposed_files=change["proposed_files"],
            patch=change["patch"],
            explanation=change["explanation"],
            tests_proposed=change["tests_proposed"],
        )
        checks = self.policy.validate(proposal)[:3]
        checks.extend(self.workspace_validator.validate(change=change, context=context))
        return self.repository.save_validations(change_id, checks=checks, actor=actor)

    def decide(
        self,
        *,
        change_id: UUID,
        actor: UUID,
        approved: bool,
        comment: str | None,
    ) -> dict:
        return self.repository.decide(
            change_id, actor=actor, approved=approved, comment=comment
        )

    async def publish(self, *, change_id: UUID, actor: UUID) -> dict:
        if self.publisher is None:
            raise ProviderNotConfiguredError(
                "No GitHub pull-request publisher is configured; no repository write occurred."
            )
        change = self.repository.get(change_id, actor=actor)
        context = self.build_context(change_id=change_id, actor=actor)
        result = await self.publisher.publish(change=change, context=context)
        return self.repository.record_pull_request(
            change_id, result=result, actor=actor
        )
