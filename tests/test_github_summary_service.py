from __future__ import annotations

import asyncio
import io
import os
import tarfile
from types import SimpleNamespace
from unittest.mock import AsyncMock


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.github_summary.github_client import GitHubRepositoryMetadata
from app.github_summary.models import BatchSummary, RepositorySummary
from app.github_summary.service import RepositorySummaryService
from app.github_summary.settings import GitHubSummarySettings


def _repository_archive() -> bytes:
    content = b"# Example\n\nA FastAPI service."
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("owner-repo-sha/README.md")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_summary_service_orchestrates_archive_scan_and_structured_output(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeGitHubClient:
        def __init__(self, _settings) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            pass

        async def get_repository(self, repository):
            return GitHubRepositoryMetadata(
                full_name=repository.full_name,
                html_url=repository.canonical_url,
                description="Example",
                visibility="public",
                default_branch="main",
                stargazers_count=1,
                forks_count=2,
                open_issues_count=3,
                archived=False,
            )

        async def get_commit_sha(self, _repository, _ref):
            return "abc123"

        async def get_languages(self, _repository):
            return {"Python": 100}

        async def download_archive(self, _repository, _ref):
            return _repository_archive()

    monkeypatch.setattr("app.github_summary.service.GitHubClient", FakeGitHubClient)
    service = RepositorySummaryService(
        GitHubSummarySettings(
            openai_api_key="test",
            database_enabled=False,
            cache_enabled=False,
            cache_directory=tmp_path,
        )
    )
    batch = BatchSummary(
        files_reviewed=["README.md"],
        overview="Example",
        components=[],
        api_endpoints=[],
        dependencies=["FastAPI"],
        data_and_storage=[],
        processing_flow=[],
        setup_observations=[],
        strengths=[],
        risks=[],
        evidence_files=["README.md"],
    )
    final = RepositorySummary(
        title="Example",
        executive_summary="Example service.",
        problem_statement="Example problem.",
        primary_capabilities=[],
        architecture=[],
        technology_stack=["FastAPI"],
        key_components=[],
        api_endpoints=[],
        data_and_storage=[],
        request_or_processing_flow=[],
        setup_and_run=[],
        strengths=[],
        risks_and_gaps=[],
        recommended_next_steps=[],
        evidence_files=["README.md"],
    )
    service._generate_structured = AsyncMock(side_effect=[batch, final])

    result = asyncio.run(
        service.summarize(repository_url="https://github.com/owner/repo")
    )

    assert result.status == "completed"
    assert result.repository.commit_sha == "abc123"
    assert result.analysis.analyzed_files == 1
    assert result.analysis.batches == 1
    assert result.summary_markdown.startswith("# Repository Summary")
    assert service._generate_structured.await_count == 2


def test_openai_structured_call_disables_storage(tmp_path) -> None:
    batch = BatchSummary(
        files_reviewed=[],
        overview="Example",
        components=[],
        api_endpoints=[],
        dependencies=[],
        data_and_storage=[],
        processing_flow=[],
        setup_observations=[],
        strengths=[],
        risks=[],
        evidence_files=[],
    )

    class FakeResponses:
        async def parse(self, **kwargs):
            assert kwargs["store"] is False
            assert kwargs["text_format"] is BatchSummary
            return SimpleNamespace(output_parsed=batch)

    service = RepositorySummaryService(
        GitHubSummarySettings(
            openai_api_key="test",
            database_enabled=False,
            cache_enabled=False,
            cache_directory=tmp_path,
        )
    )
    service._openai = SimpleNamespace(responses=FakeResponses())
    result = asyncio.run(
        service._generate_structured(
            model_type=BatchSummary,
            instructions="Analyze.",
            input_text="Evidence.",
        )
    )
    assert result is batch
