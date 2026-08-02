from __future__ import annotations

import io
import os
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.github_summary.archive import UnsafeArchiveError, extract_github_tarball
from app.github_summary.cache import SummaryCache
from app.github_summary.github_url import InvalidGitHubUrl, parse_github_repository_url
from app.github_summary.models import (
    AnalysisStatistics,
    RepositoryIdentity,
    RepositorySummary,
    RepositorySummaryResponse,
)
from app.github_summary.scanner import RepositoryScanner
from app.github_summary.security import is_sensitive_path, redact_secrets
from app.github_summary.settings import GitHubSummarySettings
from app.routes.github import get_repository_summary_service, router


def _tarball(name: str, content: bytes = b"hello", *, symlink: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name=name)
        if symlink:
            info.type = tarfile.SYMTYPE
            info.linkname = "README.md"
        else:
            info.size = len(content)
        archive.addfile(info, None if symlink else io.BytesIO(content))
    return buffer.getvalue()


def _response() -> RepositorySummaryResponse:
    summary = RepositorySummary(
        title="Example",
        executive_summary="Example repository.",
        problem_statement="Example problem.",
        primary_capabilities=[],
        architecture=[],
        technology_stack=["Python"],
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
    return RepositorySummaryResponse(
        generated_at=datetime.now(UTC),
        duration_seconds=0.1,
        repository=RepositoryIdentity(
            owner="owner",
            name="repo",
            full_name="owner/repo",
            url="https://github.com/owner/repo",
            visibility="public",
            description=None,
            default_branch="main",
            analyzed_ref="main",
            commit_sha="abc",
            language_bytes={"Python": 100},
            stars=0,
            forks=0,
            open_issues=0,
            archived=False,
        ),
        analysis=AnalysisStatistics(
            archive_bytes=100,
            discovered_files=1,
            analyzed_files=1,
            skipped_files=0,
            analyzed_characters=10,
            batches=1,
            cache_hit=False,
        ),
        summary=summary,
        summary_markdown="# Example\n",
        model="gpt-5-mini",
    )


def test_parse_repository_url() -> None:
    result = parse_github_repository_url("https://github.com/owner/repo.git")
    assert result.full_name == "owner/repo"
    assert result.canonical_url == "https://github.com/owner/repo"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://gitlab.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://token@github.com/owner/repo",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/owner%2Frepo",
    ],
)
def test_reject_invalid_repository_urls(url: str) -> None:
    with pytest.raises(InvalidGitHubUrl):
        parse_github_repository_url(url)


def test_extract_archive(tmp_path: Path) -> None:
    root = extract_github_tarball(
        _tarball("owner-repo-sha/README.md"),
        tmp_path,
        max_extracted_bytes=1000,
    )
    assert (root / "README.md").read_text(encoding="utf-8") == "hello"


@pytest.mark.parametrize("name", ["../outside.txt", "/absolute.txt"])
def test_reject_unsafe_archive_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(UnsafeArchiveError):
        extract_github_tarball(_tarball(name), tmp_path, max_extracted_bytes=1000)


def test_reject_archive_links(tmp_path: Path) -> None:
    with pytest.raises(UnsafeArchiveError):
        extract_github_tarball(
            _tarball("owner/repo-link", symlink=True),
            tmp_path,
            max_extracted_bytes=1000,
        )


def test_sensitive_paths_and_redaction() -> None:
    assert is_sensitive_path("config/.env")
    assert not is_sensitive_path(".env.example")
    token = "github_pat_abcdefghijklmnopqrstuvwxyz123456"
    assert token not in redact_secrets(f"TOKEN='{token}'")


def test_scanner_filters_secrets_and_prioritizes_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Example\nArchitecture", encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text("def health():\n    return True\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    settings = GitHubSummarySettings(
        openai_api_key="test",
        max_summary_files=10,
        max_total_summary_characters=100_000,
        max_file_characters=50_000,
    )
    snapshot = RepositoryScanner(settings).scan(tmp_path)
    paths = [item.path for item in snapshot.files]
    assert "README.md" in paths
    assert "app/main.py" in paths
    assert ".env" not in paths


def test_cache_round_trip(tmp_path: Path) -> None:
    cache = SummaryCache(enabled=True, directory=tmp_path, ttl_seconds=60)
    cache.set("key", {"result": True})
    assert cache.get("key") == {"result": True}


def test_summary_route_uses_integrated_service() -> None:
    class FakeService:
        async def summarize(self, **_: object) -> RepositorySummaryResponse:
            return _response()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_summary_service] = lambda: FakeService()
    client = TestClient(app)
    response = client.post(
        "/api/v1/github/summary",
        json={"repository_url": "https://github.com/owner/repo"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["repository"]["full_name"] == "owner/repo"

