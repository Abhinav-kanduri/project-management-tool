import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from psycopg.errors import UndefinedTable
import pytest

from app.github_summary.github_client import GitHubClient
from app.github_summary.github_url import parse_github_repository_url
from app.github_summary.settings import GitHubSummarySettings
from app.main import app
from app.impact_analysis.repositories.snapshots import SnapshotRepository
from app.impact_analysis.services.repository_branches import (
    RepositoryBranchService,
    RepositoryLinkHasDependencies,
)


def test_github_branch_listing_reads_every_page() -> None:
    client = GitHubClient(GitHubSummarySettings())
    calls = []

    async def get_json(path, *, params=None):
        calls.append((path, params))
        if params["page"] == 1:
            return [
                {"name": f"branch-{index}", "commit": {"sha": str(index)}}
                for index in range(100)
            ]
        return [{"name": "last", "commit": {"sha": "last-sha"}}]

    client._get_json = get_json
    reference = parse_github_repository_url("https://github.com/example/backend")

    async def run():
        try:
            return await client.list_branches(reference)
        finally:
            await client.aclose()

    branches = asyncio.run(run())
    assert len(branches) == 101
    assert branches[-1]["name"] == "last"
    assert [params["page"] for _, params in calls] == [1, 2]


def test_github_branch_listing_stops_after_partial_first_page() -> None:
    client = GitHubClient(GitHubSummarySettings())
    calls = []

    async def get_json(path, *, params=None):
        calls.append(params)
        return [{"name": "main", "commit": {"sha": "abc"}}]

    client._get_json = get_json
    reference = parse_github_repository_url("https://github.com/example/backend")

    async def run():
        try:
            return await client.list_branches(reference)
        finally:
            await client.aclose()

    assert asyncio.run(run())[0]["name"] == "main"
    assert len(calls) == 1


def test_project_repository_branch_refresh_and_sync_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    snapshot_id = UUID("10000000-0000-0000-0000-000000000001")

    class FakeBranchService:
        async def list(self, **_kwargs):
            return {
                "branches": [
                    {
                        "name": "feature/all-branches",
                        "commit_sha": "a" * 40,
                        "protected": False,
                        "snapshot_id": snapshot_id,
                        "sync_status": "COMPLETED",
                        "last_synced_at": now,
                    }
                ],
                "refreshed_at": now,
            }

        async def sync(self, **kwargs):
            assert kwargs["branch"] == "feature/all-branches"
            assert kwargs["force_refresh"] is True
            return {
                "snapshot_id": snapshot_id,
                "branch": kwargs["branch"],
                "commit_sha": "a" * 40,
                "status": "COMPLETED",
                "cache_hit": False,
                "synced_at": now,
                "discovered_files": 12,
                "indexed_files": 10,
                "skipped_files": 2,
                "coverage_percent": 83.33,
            }

    monkeypatch.setattr(
        "app.routes.impact_selectors.RepositoryBranchService", FakeBranchService
    )
    client = TestClient(app)
    repository_id = "20000000-0000-0000-0000-000000000001"
    headers = {"X-Actor": "30000000-0000-0000-0000-000000000001"}

    refreshed = client.get(
        f"/api/v1/github/project-repositories/{repository_id}/branches",
        headers=headers,
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["branches"][0]["last_synced_at"] == now.isoformat().replace(
        "+00:00", "Z"
    )

    synced = client.post(
        f"/api/v1/github/project-repositories/{repository_id}/sync",
        headers=headers,
        json={"branch": "feature/all-branches", "force_refresh": True},
    )
    assert synced.status_code == 200
    assert synced.json()["indexed_files"] == 10
    assert synced.json()["branch"] == "feature/all-branches"


def test_project_repository_sync_rejects_control_characters() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/github/project-repositories/20000000-0000-0000-0000-000000000001/sync",
        headers={"X-Actor": "30000000-0000-0000-0000-000000000001"},
        json={"branch": "main\nmalicious"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"


def test_branch_refresh_survives_pending_snapshot_migrations() -> None:
    def missing_schema():
        raise UndefinedTable("repository_snapshots is not deployed")

    repository = SnapshotRepository(connection_factory=missing_schema)
    assert repository.latest_by_commit(
        UUID("20000000-0000-0000-0000-000000000001")
    ) == {}


def test_project_repository_unlink_contract(monkeypatch) -> None:
    class FakeBranchService:
        def unlink(self, **kwargs):
            return {
                "unlinked": True,
                "project_repository_id": kwargs["project_repository_id"],
                "project_id": UUID("40000000-0000-0000-0000-000000000001"),
                "repository_full_name": "example/backend",
            }

    monkeypatch.setattr(
        "app.routes.impact_selectors.RepositoryBranchService", FakeBranchService
    )
    client = TestClient(app)
    response = client.delete(
        "/api/v1/github/project-repositories/20000000-0000-0000-0000-000000000001",
        headers={"X-Actor": "30000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "unlinked": True,
        "project_repository_id": "20000000-0000-0000-0000-000000000001",
        "project_id": "40000000-0000-0000-0000-000000000001",
        "repository_full_name": "example/backend",
    }


def test_repository_unlink_refuses_to_delete_persisted_history(monkeypatch) -> None:
    class Cursor:
        def __init__(self):
            self.statements = []
            self.responses = [
                {
                    "project_repository_id": UUID(
                        "20000000-0000-0000-0000-000000000001"
                    ),
                    "project_id": UUID("40000000-0000-0000-0000-000000000001"),
                    "repository_full_name": "example/backend",
                },
                {"role": "PROJECT_ADMIN"},
                {"present": True},
                {"total": 1},
                {"present": False},
            ]

        def execute(self, statement, _parameters=()):
            self.statements.append(" ".join(statement.split()).lower())

        def fetchone(self):
            return self.responses.pop(0)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            raise AssertionError("A dependency conflict must not commit")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    connection = Connection()
    monkeypatch.setattr(
        "app.impact_analysis.services.repository_branches.get_connection",
        lambda: connection,
    )
    with pytest.raises(RepositoryLinkHasDependencies) as raised:
        RepositoryBranchService().unlink(
            project_repository_id=UUID("20000000-0000-0000-0000-000000000001"),
            actor=UUID("30000000-0000-0000-0000-000000000001"),
        )
    assert raised.value.dependencies == {"repository_snapshots": 1}
    assert not any(
        statement.startswith("delete from project_github_repositories")
        for statement in connection.cursor_instance.statements
    )
