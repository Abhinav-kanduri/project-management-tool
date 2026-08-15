from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.github_summary.scanner import IGNORED_DIRECTORIES, RepositoryScanner
from app.github_summary.security import is_sensitive_path, redact_secrets
from app.github_summary.settings import GitHubSummarySettings
from app.impact_analysis.repositories.source_index import SourceIndexRepository
from app.impact_analysis.source.models import ParsedSourceFile
from app.impact_analysis.source.parsers.registry import SourceParserRegistry


@dataclass(frozen=True)
class SourceIndexResult:
    discovered_files: int
    indexed_files: int
    skipped_files: int
    parsed_files: list[ParsedSourceFile]
    counts: dict[str, int]

    @property
    def coverage_percent(self) -> float:
        eligible = self.indexed_files + self.skipped_files
        return round(100 * self.indexed_files / eligible, 2) if eligible else 0


class SourceIndexer:
    def __init__(
        self,
        *,
        repository: SourceIndexRepository | None = None,
        registry: SourceParserRegistry | None = None,
        settings: GitHubSummarySettings | None = None,
    ) -> None:
        self.repository = repository or SourceIndexRepository()
        self.registry = registry or SourceParserRegistry()
        self.settings = settings or GitHubSummarySettings()

    def index_root(
        self,
        *,
        snapshot_id: UUID,
        root: Path,
        before_persist: Callable[[], None] | None = None,
    ) -> SourceIndexResult:
        candidates = []
        discovered = 0
        skipped = 0
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            discovered += 1
            relative = path.relative_to(root)
            relative_text = relative.as_posix()
            if any(part.casefold() in IGNORED_DIRECTORIES for part in relative.parts):
                continue
            if is_sensitive_path(relative_text) or not RepositoryScanner._is_supported(path):
                continue
            try:
                if path.stat().st_size > self.settings.max_file_bytes:
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            candidates.append(path)
        candidates.sort(key=lambda item: item.relative_to(root).as_posix())
        if len(candidates) > self.settings.max_scanned_files:
            skipped += len(candidates) - self.settings.max_scanned_files
            candidates = candidates[: self.settings.max_scanned_files]

        parsed = []
        for path in candidates:
            content = RepositoryScanner._read_text(path)
            if content is None:
                skipped += 1
                continue
            relative = path.relative_to(root).as_posix()
            language = RepositoryScanner._language_for(path)
            parsed.append(
                self.registry.parse(
                    path=relative,
                    content=redact_secrets(content),
                    language=language,
                )
            )
        if before_persist is not None:
            before_persist()
        counts = self.repository.replace(snapshot_id, parsed)
        return SourceIndexResult(
            discovered_files=discovered,
            indexed_files=len(parsed),
            skipped_files=skipped,
            parsed_files=parsed,
            counts=counts,
        )
