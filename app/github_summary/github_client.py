from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.github_summary.github_url import GitHubRepositoryRef
from app.github_summary.settings import GitHubSummarySettings


class GitHubApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubRepositoryMetadata:
    full_name: str
    html_url: str
    description: str | None
    visibility: str | None
    default_branch: str
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    archived: bool


@dataclass(frozen=True)
class GitHubRepositoryRecord:
    id: int
    node_id: str | None
    owner: str
    name: str
    full_name: str
    repository_url: str
    description: str | None
    default_branch: str
    visibility: str
    private: bool
    archived: bool
    fork: bool
    pushed_at: datetime | None
    updated_at: datetime | None


class GitHubClient:
    def __init__(self, settings: GitHubSummarySettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(follow_redirects=True)

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self._settings.github_api_version,
            "User-Agent": "ReleaseLens-GitHub-Repository-Summary/1.0",
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self._settings.github_api_base_url.rstrip('/')}/{path.lstrip('/')}"

    async def _get_json(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> dict | list:
        try:
            response = await self._client.get(
                self._url(path),
                headers=self._headers(),
                params=params,
                timeout=self._settings.github_request_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GitHubApiError("Could not reach the GitHub API") from exc
        self._raise_for_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubApiError("GitHub returned an invalid JSON response") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429 or (
            response.status_code == 403
            and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise GitHubApiError("GitHub API rate limit was reached", status_code=429)
        if response.status_code == 401:
            raise GitHubApiError("GitHub rejected the configured token", status_code=401)
        if response.status_code == 403:
            raise GitHubApiError(
                "GitHub denied access or the API rate limit was reached", status_code=403
            )
        if response.status_code == 404:
            raise GitHubApiError(
                "Repository was not found or the token cannot access it", status_code=404
            )
        if response.is_error:
            raise GitHubApiError(
                f"GitHub API request failed with status {response.status_code}",
                status_code=response.status_code,
            )

    async def get_repository(
        self, repository: GitHubRepositoryRef
    ) -> GitHubRepositoryMetadata:
        payload = await self._get_json(f"repos/{repository.owner}/{repository.repository}")
        if not isinstance(payload, dict):
            raise GitHubApiError("Unexpected repository response from GitHub")
        return GitHubRepositoryMetadata(
            full_name=str(payload.get("full_name", repository.full_name)),
            html_url=str(payload.get("html_url", repository.canonical_url)),
            description=payload.get("description"),
            visibility=payload.get("visibility"),
            default_branch=str(payload.get("default_branch", "main")),
            stargazers_count=int(payload.get("stargazers_count", 0)),
            forks_count=int(payload.get("forks_count", 0)),
            open_issues_count=int(payload.get("open_issues_count", 0)),
            archived=bool(payload.get("archived", False)),
        )

    async def list_repositories(
        self, *, page: int = 1, per_page: int = 100
    ) -> list[GitHubRepositoryRecord]:
        payload = await self._get_json(
            "user/repos",
            params={
                "affiliation": "owner,collaborator,organization_member",
                "sort": "updated",
                "direction": "desc",
                "page": page,
                "per_page": per_page,
            },
        )
        if not isinstance(payload, list):
            raise GitHubApiError("Unexpected repository list response from GitHub")
        return [self._repository_record(item) for item in payload if isinstance(item, dict)]

    async def get_repository_by_id(self, repository_id: int) -> GitHubRepositoryRecord:
        payload = await self._get_json(f"repositories/{repository_id}")
        if not isinstance(payload, dict):
            raise GitHubApiError("Unexpected repository response from GitHub")
        return self._repository_record(payload)

    @staticmethod
    def _repository_record(payload: dict[str, Any]) -> GitHubRepositoryRecord:
        owner = payload.get("owner") if isinstance(payload.get("owner"), dict) else {}
        repository_id = payload.get("id")
        name = str(payload.get("name") or "").strip()
        owner_login = str(owner.get("login") or "").strip()
        full_name = str(payload.get("full_name") or "").strip()
        repository_url = str(payload.get("html_url") or "").strip()
        if not isinstance(repository_id, int) or repository_id < 1:
            raise GitHubApiError("GitHub returned a repository without a valid ID")
        if not name or not owner_login or not full_name or not repository_url:
            raise GitHubApiError("GitHub returned incomplete repository metadata")
        private = bool(payload.get("private", False))
        return GitHubRepositoryRecord(
            id=repository_id,
            node_id=str(payload["node_id"]) if payload.get("node_id") else None,
            owner=owner_login,
            name=name,
            full_name=full_name,
            repository_url=repository_url,
            description=(
                str(payload["description"]) if payload.get("description") else None
            ),
            default_branch=str(payload.get("default_branch") or "main"),
            visibility=str(payload.get("visibility") or ("private" if private else "public")),
            private=private,
            archived=bool(payload.get("archived", False)),
            fork=bool(payload.get("fork", False)),
            pushed_at=_parse_github_datetime(payload.get("pushed_at")),
            updated_at=_parse_github_datetime(payload.get("updated_at")),
        )

    async def get_languages(self, repository: GitHubRepositoryRef) -> dict[str, int]:
        payload = await self._get_json(
            f"repos/{repository.owner}/{repository.repository}/languages"
        )
        if not isinstance(payload, dict):
            return {}
        return {str(key): int(value) for key, value in payload.items()}

    async def get_commit_sha(self, repository: GitHubRepositoryRef, ref: str) -> str | None:
        encoded_ref = quote(ref, safe="")
        payload = await self._get_json(
            f"repos/{repository.owner}/{repository.repository}/commits/{encoded_ref}"
        )
        return str(payload.get("sha")) if isinstance(payload, dict) else None

    async def download_archive(self, repository: GitHubRepositoryRef, ref: str) -> bytes:
        encoded_ref = quote(ref, safe="")
        path = f"repos/{repository.owner}/{repository.repository}/tarball/{encoded_ref}"
        chunks: list[bytes] = []
        downloaded = 0
        try:
            async with self._client.stream(
                "GET",
                self._url(path),
                headers=self._headers(),
                timeout=self._settings.github_archive_timeout_seconds,
            ) as response:
                self._raise_for_status(response)
                async for chunk in response.aiter_bytes():
                    downloaded += len(chunk)
                    if downloaded > self._settings.max_archive_bytes:
                        raise GitHubApiError("Repository archive exceeds the configured limit")
                    chunks.append(chunk)
        except GitHubApiError:
            raise
        except httpx.HTTPError as exc:
            raise GitHubApiError("Could not download the repository archive") from exc
        return b"".join(chunks)


def _parse_github_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
