from uuid import uuid4

import pytest

from app.impact_analysis.remediation.models import ChangeProposal, ProposedFile
from app.impact_analysis.remediation.policy import PatchPolicy
from app.impact_analysis.remediation.prompt import RemediationPromptService
from app.impact_analysis.remediation.service import (
    ProviderNotConfiguredError,
    RemediationService,
)


def proposal(path: str = "app/service.py", body: str = "+safe = True") -> ChangeProposal:
    return ChangeProposal(
        proposed_files=[ProposedFile(path=path, action="MODIFY")],
        patch=(
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1 +1,2 @@\n"
            " existing = True\n"
            f"{body}\n"
        ),
        explanation="Complete the missing behavior.",
        tests_proposed=["tests/test_service.py"],
    )


def test_patch_policy_accepts_safe_relative_unified_diff() -> None:
    checks = PatchPolicy().validate(proposal())
    by_type = {item.check_type: item for item in checks}
    assert by_type["PATH_SAFETY"].status == "PASSED"
    assert by_type["FORMAT"].status == "PASSED"
    assert by_type["POLICY"].status == "PASSED"
    assert by_type["UNIT_TEST"].status == "SKIPPED"


@pytest.mark.parametrize("path", ["../outside.py", ".env", ".github/workflows/release.yml"])
def test_patch_policy_rejects_unsafe_or_restricted_paths(path: str) -> None:
    checks = PatchPolicy().validate(proposal(path=path))
    assert checks[0].status == "FAILED"


def test_patch_policy_rejects_secrets_and_destructive_sql() -> None:
    secret = PatchPolicy().validate(proposal(body="+OPENAI_API_KEY=secret"))
    destructive = PatchPolicy().validate(
        proposal(path="sql/change.sql", body="+DROP SCHEMA public")
    )
    assert secret[2].status == "FAILED"
    assert destructive[2].status == "FAILED"


def test_generation_requires_explicit_provider() -> None:
    with pytest.raises(ProviderNotConfiguredError, match="not transferred"):
        RemediationService().generate(change_id=uuid4(), actor=uuid4())


def test_validation_requires_isolated_workspace_adapter() -> None:
    with pytest.raises(ProviderNotConfiguredError, match="approval remains blocked"):
        RemediationService().validate(change_id=uuid4(), actor=uuid4())


def test_remediation_api_requires_explicit_uuid_actor_header() -> None:
    from app.main import app

    operation = app.openapi()["paths"][
        "/api/v1/impact-analysis/findings/{finding_id}/generated-changes"
    ]["post"]
    actor = next(
        parameter for parameter in operation["parameters"] if parameter["name"] == "X-Actor"
    )
    assert actor["required"] is True
    assert actor["schema"]["format"] == "uuid"


def test_copilot_prompt_uses_persisted_context_without_a_generation_provider() -> None:
    run_id = uuid4()
    finding_id = uuid4()

    class Repository:
        def load(self, **values):
            assert values["actor"] == "local-impact-analysis"
            return {
                "source_repository": "example/customer-support",
                "source_ref": "feature/july26th",
                "commit_sha": "a" * 40,
                "finding_status": "MISSING",
                "what_present": "The request endpoint exists.",
                "what_missing": "Conversation persistence is absent.",
                "technical_reason": "No database write was found.",
                "recommendation": "Persist the conversation before returning.",
                "requirement_key": "REQ-004",
                "requirement_text": "Authenticated requests must persist conversations.",
                "requirement_type": "DATA_PERSISTENCE",
                "applicability": "STATICALLY_VERIFIABLE",
                "expected_predicates": [
                    {
                        "predicate_type": "PERSISTENCE_EXISTS",
                        "subject": "conversation",
                    }
                ],
                "evidence": [
                    {
                        "evidence_type": "SOURCE_CODE",
                        "direction": "CONTEXT",
                        "file_path": "app/routes/chat.py",
                        "start_line": 42,
                        "end_line": 57,
                        "description": "The endpoint constructs a response.",
                        "excerpt": "def create_conversation(): ...",
                    }
                ],
                "related_requirements": [],
                "target_repository": {
                    "name": "example/customer-support",
                    "default_branch": "main",
                },
            }

    result = RemediationPromptService(Repository()).generate(
        run_id=run_id,
        finding_id=finding_id,
        actor="local-impact-analysis",
        target_repository="example/customer-support",
        target_ref="feature/july26th",
        include_related_requirements=True,
        include_test_plan=True,
        include_repository_warning=True,
    )

    assert result["target"] == "github_copilot_chat"
    assert result["repository_suitability"] == "suitable"
    assert result["source_repository"]["commit_sha"] == "a" * 40
    assert "REQ-004" in result["prompt"]
    assert "app/routes/chat.py:42-57" in result["prompt"]
    assert "do not claim tests passed unless executed" in result["prompt"]
    assert len(result["prompt_hash"]) == 64
