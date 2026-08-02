from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


class InvalidGitHubUrl(ValueError):
    pass


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    repository: str
    canonical_url: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repository}"


_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def parse_github_repository_url(
    raw_url: str,
    *,
    allowed_hosts: frozenset[str] | set[str] | None = None,
) -> GitHubRepositoryRef:
    allowed = allowed_hosts or {"github.com", "www.github.com"}
    try:
        parsed = urlparse(raw_url.strip())
        port = parsed.port
    except ValueError as exc:
        raise InvalidGitHubUrl("Malformed GitHub repository URL") from exc

    if parsed.scheme.lower() != "https":
        raise InvalidGitHubUrl("Only HTTPS GitHub repository URLs are accepted")
    if parsed.username or parsed.password or (port is not None and port != 443):
        raise InvalidGitHubUrl("Credentials and custom ports are not accepted")
    if parsed.query or parsed.fragment:
        raise InvalidGitHubUrl("Repository URLs cannot contain query strings or fragments")

    hostname = (parsed.hostname or "").lower()
    if hostname not in allowed:
        raise InvalidGitHubUrl(f"Unsupported GitHub host: {hostname or 'missing'}")

    if "%2f" in parsed.path.lower() or "%5c" in parsed.path.lower():
        raise InvalidGitHubUrl("Encoded path separators are not accepted")
    decoded_path = unquote(parsed.path)
    path_parts = [part for part in decoded_path.split("/") if part]
    if len(path_parts) != 2:
        raise InvalidGitHubUrl(
            "Use a repository root URL such as https://github.com/owner/repository"
        )

    owner, repository = path_parts
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not _OWNER_PATTERN.fullmatch(owner) or not _REPOSITORY_PATTERN.fullmatch(repository):
        raise InvalidGitHubUrl("Invalid GitHub repository owner or name")
    if repository in {".", ".."}:
        raise InvalidGitHubUrl("Invalid GitHub repository path")

    return GitHubRepositoryRef(
        owner=owner,
        repository=repository,
        canonical_url=f"https://github.com/{owner}/{repository}",
    )

