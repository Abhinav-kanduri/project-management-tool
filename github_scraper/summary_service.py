from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.config import Settings
from app.utils.github_url import GitHubRepositoryRef


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


class GitHubClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self._settings.github_api_version,
            "User-Agent": "ReleaseMind-GitHub-Repository-Summary/1.0",
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        return headers

    async def _get_json(self, path: str) -> dict | list:
        url = f"{self._settings.github_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.github_request_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise GitHubApiError("Could not reach the GitHub API") from exc

        if response.status_code == 401:
            raise GitHubApiError(
                "GitHub rejected the token. Check that GITHUB_TOKEN is valid.",
                status_code=401,
            )
        if response.status_code == 403:
            message = "GitHub denied access or the API rate limit was reached"
            raise GitHubApiError(message, status_code=403)
        if response.status_code == 404:
            raise GitHubApiError(
                "Repository was not found or the token cannot access it",
                status_code=404,
            )
        if response.is_error:
            raise GitHubApiError(
                f"GitHub API request failed with status {response.status_code}",
                status_code=response.status_code,
            )
        return response.json()

    async def get_repository(
        self, repository: GitHubRepositoryRef
    ) -> GitHubRepositoryMetadata:
        payload = await self._get_json(
            f"repos/{repository.owner}/{repository.repository}"
        )
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

    async def get_languages(
        self, repository: GitHubRepositoryRef
    ) -> dict[str, int]:
        payload = await self._get_json(
            f"repos/{repository.owner}/{repository.repository}/languages"
        )
        if not isinstance(payload, dict):
            return {}
        return {str(key): int(value) for key, value in payload.items()}

    async def get_commit_sha(
        self,
        repository: GitHubRepositoryRef,
        ref: str,
    ) -> str | None:
        encoded_ref = quote(ref, safe="")
        payload = await self._get_json(
            f"repos/{repository.owner}/{repository.repository}/commits/{encoded_ref}"
        )
        return str(payload.get("sha")) if isinstance(payload, dict) else None

    async def download_archive(
        self,
        repository: GitHubRepositoryRef,
        ref: str,
    ) -> bytes:
        encoded_ref = quote(ref, safe="")
        url = (
            f"{self._settings.github_api_base_url.rstrip('/')}/repos/"
            f"{repository.owner}/{repository.repository}/tarball/{encoded_ref}"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.github_archive_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise GitHubApiError("Could not download the repository archive") from exc

        if response.status_code in {401, 403, 404}:
            raise GitHubApiError(
                "Repository archive is unavailable. Verify the token permissions and ref.",
                status_code=response.status_code,
            )
        if response.is_error:
            raise GitHubApiError(
                f"Repository download failed with status {response.status_code}",
                status_code=response.status_code,
            )

        content = response.content
        if len(content) > self._settings.max_archive_bytes:
            raise GitHubApiError(
                f"Repository archive exceeds the configured limit of "
                f"{self._settings.max_archive_bytes} bytes"
            )
        return content
