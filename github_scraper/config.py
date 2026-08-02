from dataclasses import dataclass
from urllib.parse import urlparse


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


def parse_github_repository_url(
    raw_url: str,
    *,
    allowed_hosts: set[str] | None = None,
) -> GitHubRepositoryRef:
    """Parse a GitHub repository URL and reject nested or ambiguous paths."""

    allowed = allowed_hosts or {"github.com", "www.github.com"}
    parsed = urlparse(raw_url.strip())

    if parsed.scheme.lower() != "https":
        raise InvalidGitHubUrl("Only HTTPS GitHub repository URLs are accepted")

    hostname = (parsed.hostname or "").lower()
    if hostname not in allowed:
        raise InvalidGitHubUrl(f"Unsupported GitHub host: {hostname or 'missing'}")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise InvalidGitHubUrl(
            "Use a repository root URL such as https://github.com/owner/repository"
        )

    owner, repository = path_parts
    if repository.endswith(".git"):
        repository = repository[:-4]

    if not owner or not repository:
        raise InvalidGitHubUrl("Repository owner and name are required")

    if any(segment in {".", ".."} for segment in (owner, repository)):
        raise InvalidGitHubUrl("Invalid repository path")

    canonical_url = f"https://github.com/{owner}/{repository}"
    return GitHubRepositoryRef(owner, repository, canonical_url)
