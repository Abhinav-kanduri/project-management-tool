import pytest

from app.utils.github_url import InvalidGitHubUrl, parse_github_repository_url


def test_parse_repository_url():
    result = parse_github_repository_url(
        "https://github.com/Abhinav-kanduri/Customer-Support-AI-Chatbot"
    )
    assert result.owner == "Abhinav-kanduri"
    assert result.repository == "Customer-Support-AI-Chatbot"
    assert result.full_name == "Abhinav-kanduri/Customer-Support-AI-Chatbot"


def test_parse_dot_git_suffix():
    result = parse_github_repository_url("https://github.com/owner/repo.git")
    assert result.repository == "repo"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://gitlab.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner",
    ],
)
def test_reject_invalid_urls(url: str):
    with pytest.raises(InvalidGitHubUrl):
        parse_github_repository_url(url)
