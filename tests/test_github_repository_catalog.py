from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.github_summary.catalog import (
    GitHubRepositoryCatalog,
    GitHubRepositoryCatalogService,
)
from app.github_summary.catalog_models import (
    GitHubRepositoryListResponse,
    GitHubRepositoryOption,
    ImportedGitHubRepository,
)
from app.github_summary.github_client import GitHubRepositoryRecord
from app.github_summary.settings import GitHubSummarySettings
from app.routes.github import get_repository_catalog_service, router


def _record() -> GitHubRepositoryRecord:
    now = datetime.now(UTC)
    return GitHubRepositoryRecord(
        id=123456,
        node_id="R_test",
        owner="owner",
        name="repository",
        full_name="owner/repository",
        repository_url="https://github.com/owner/repository",
        description="Example",
        default_branch="main",
        visibility="private",
        private=True,
        archived=False,
        fork=False,
        pushed_at=now,
        updated_at=now,
    )


def test_catalog_service_lists_stable_github_ids_and_linked_state(monkeypatch) -> None:
    record = _record()

    class FakeGitHubClient:
        def __init__(self, _settings):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def list_repositories(self, *, page, per_page):
            assert (page, per_page) == (1, 100)
            return [record]

    monkeypatch.setattr("app.github_summary.catalog.GitHubClient", FakeGitHubClient)
    service = GitHubRepositoryCatalogService(
        GitHubSummarySettings(
            github_token="test-token", openai_api_key="test", database_enabled=False
        )
    )
    project_id = uuid4()
    association_id = uuid4()
    catalog_id = uuid4()
    monkeypatch.setattr(
        service.catalog,
        "linked_by_github_id",
        lambda _project_id: {
            record.id: {
                "association_id": association_id,
                "catalog_repository_id": catalog_id,
            }
        },
    )

    result = asyncio.run(
        service.list_repositories(page=1, per_page=100, project_id=project_id)
    )
    assert result.repositories[0].id == 123456
    assert result.repositories[0].full_name == "owner/repository"
    assert result.repositories[0].imported is True
    assert result.repositories[0].association_id == association_id


def test_catalog_persists_repository_with_validated_workspace_scope(monkeypatch) -> None:
    product_space_id = uuid4()
    project_id = uuid4()
    catalog_id = uuid4()
    association_id = uuid4()
    now = datetime.now(UTC)
    statements: list[str] = []
    rows = iter(
        [
            {
                "project_id": project_id,
                "project_name": "Project",
                "product_space_id": product_space_id,
                "product_space_name": "Product Space",
            },
            {"id": catalog_id, "synced_at": now},
            {"id": association_id, "linked_at": now},
        ]
    )

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters=None):
            statements.append(" ".join(statement.split()).lower())

        def fetchone(self):
            return next(rows)

    class FakeConnection:
        commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            self.commits += 1

    connection = FakeConnection()
    monkeypatch.setattr(
        "app.github_summary.catalog.get_connection", lambda: connection
    )

    result = GitHubRepositoryCatalog().import_repository(
        _record(), product_space_id=product_space_id, project_id=project_id
    )
    assert "join product_spaces" in statements[0]
    assert statements[1].startswith("insert into github_repositories")
    assert statements[2].startswith("insert into project_github_repositories")
    assert result["github_repository_id"] == 123456
    assert result["project_id"] == project_id
    assert connection.commits == 1


def test_repository_catalog_routes_support_dropdown_and_import() -> None:
    product_space_id = uuid4()
    project_id = uuid4()
    association_id = uuid4()
    catalog_id = uuid4()
    now = datetime.now(UTC)

    class FakeService:
        async def list_repositories(self, **_kwargs):
            return GitHubRepositoryListResponse(
                page=1,
                per_page=100,
                returned=1,
                has_next_page=False,
                repositories=[GitHubRepositoryOption(**_record().__dict__)],
            )

        async def import_repository(self, **_kwargs):
            return ImportedGitHubRepository(
                association_id=association_id,
                catalog_repository_id=catalog_id,
                github_repository_id=123456,
                product_space_id=product_space_id,
                product_space_name="Product Space",
                project_id=project_id,
                project_name="Project",
                owner="owner",
                name="repository",
                full_name="owner/repository",
                repository_url="https://github.com/owner/repository",
                description="Example",
                default_branch="main",
                visibility="private",
                private=True,
                archived=False,
                linked_at=now,
                synced_at=now,
            )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_catalog_service] = lambda: FakeService()
    client = TestClient(app)

    listed = client.get(
        f"/api/v1/github/repositories?project_id={project_id}&per_page=100"
    )
    assert listed.status_code == 200
    assert listed.json()["repositories"][0]["id"] == 123456

    imported = client.post(
        "/api/v1/github/repositories/import",
        json={
            "github_repository_id": 123456,
            "product_space_id": str(product_space_id),
            "project_id": str(project_id),
        },
    )
    assert imported.status_code == 201
    assert imported.json()["project_id"] == str(project_id)


def test_repository_catalog_migration_has_required_links() -> None:
    migration = Path("sql/github_repository_catalog.sql").read_text(encoding="utf-8")
    assert "create table if not exists public.github_repositories" in migration.lower()
    assert "create table if not exists public.project_github_repositories" in migration.lower()
    assert "references public.product_spaces(id) on delete cascade" in migration.lower()
    assert "references public.projects(id) on delete cascade" in migration.lower()
