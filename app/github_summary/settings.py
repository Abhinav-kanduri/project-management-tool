from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.config import (
    DATABASE_URL,
    OPENAI_API_KEY,
    OPENAI_CHAT_MODEL,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
    PROJECT_ROOT,
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GitHubSummarySettings:
    github_token: str | None = field(default_factory=lambda: os.getenv("GITHUB_TOKEN"))
    github_api_base_url: str = field(
        default_factory=lambda: os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
    )
    github_api_version: str = field(
        default_factory=lambda: os.getenv("GITHUB_API_VERSION", "2026-03-10")
    )
    github_request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("GITHUB_REQUEST_TIMEOUT_SECONDS", "30"))
    )
    github_archive_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("GITHUB_ARCHIVE_TIMEOUT_SECONDS", "120"))
    )
    openai_api_key: str = OPENAI_API_KEY
    openai_model: str = field(
        default_factory=lambda: os.getenv(
            "GITHUB_SUMMARY_MODEL", os.getenv("OPENAI_MODEL", OPENAI_CHAT_MODEL)
        )
    )
    openai_max_output_tokens: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_OUTPUT_TOKENS", "5000"))
    )
    openai_request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("GITHUB_SUMMARY_OPENAI_TIMEOUT_SECONDS", "120"))
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL)
    )
    embedding_dimensions: int = field(
        default_factory=lambda: int(
            os.getenv("EMBEDDING_DIMENSIONS", str(OPENAI_EMBEDDING_DIMENSIONS))
        )
    )
    embedding_batch_size: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))
    )
    embedding_max_retries: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    )
    embedding_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60"))
    )
    database_enabled: bool = field(
        default_factory=lambda: _env_bool("DATABASE_ENABLED", True)
    )
    database_url: str = DATABASE_URL
    output_directory: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIRECTORY", "artifacts"))
    )
    summary_chunk_target_tokens: int = field(
        default_factory=lambda: int(os.getenv("SUMMARY_CHUNK_TARGET_TOKENS", "600"))
    )
    summary_chunk_overlap_tokens: int = field(
        default_factory=lambda: int(os.getenv("SUMMARY_CHUNK_OVERLAP_TOKENS", "80"))
    )
    summary_chunk_min_tokens: int = field(
        default_factory=lambda: int(os.getenv("SUMMARY_CHUNK_MIN_TOKENS", "80"))
    )
    summary_format_version: str = field(
        default_factory=lambda: os.getenv("GITHUB_SUMMARY_FORMAT_VERSION", "2")
    )
    max_archive_bytes: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_ARCHIVE_BYTES", "157286400"))
    )
    max_extracted_bytes: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_EXTRACTED_BYTES", "524288000"))
    )
    max_file_bytes: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_FILE_BYTES", "1048576"))
    )
    max_scanned_files: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_SCANNED_FILES", "1500"))
    )
    max_summary_files: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_FILES", "120"))
    )
    max_file_characters: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_FILE_CHARACTERS", "24000"))
    )
    max_total_summary_characters: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_MAX_CHARACTERS", "350000"))
    )
    summary_batch_characters: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_BATCH_CHARACTERS", "45000"))
    )
    cache_enabled: bool = field(
        default_factory=lambda: _env_bool("GITHUB_SUMMARY_CACHE_ENABLED", True)
    )
    cache_directory: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "GITHUB_SUMMARY_CACHE_DIRECTORY",
                str(PROJECT_ROOT / ".cache" / "github-summary"),
            )
        )
    )
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("GITHUB_SUMMARY_CACHE_TTL_SECONDS", "86400"))
    )
    allowed_hosts: frozenset[str] = frozenset({"github.com", "www.github.com"})

    def __post_init__(self) -> None:
        if self.embedding_dimensions < 1:
            raise ValueError("EMBEDDING_DIMENSIONS must be positive")
        if self.embedding_batch_size < 1:
            raise ValueError("EMBEDDING_BATCH_SIZE must be positive")
        if self.embedding_max_retries < 0:
            raise ValueError("EMBEDDING_MAX_RETRIES cannot be negative")
        if not 0 <= self.summary_chunk_overlap_tokens < self.summary_chunk_target_tokens:
            raise ValueError("SUMMARY_CHUNK_OVERLAP_TOKENS must be smaller than the target")
        if not 1 <= self.summary_chunk_min_tokens <= self.summary_chunk_target_tokens:
            raise ValueError("SUMMARY_CHUNK_MIN_TOKENS must not exceed the target")
        if self.database_enabled and not self.database_url:
            raise ValueError("DATABASE_URL is required when DATABASE_ENABLED=true")
