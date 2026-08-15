from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from app.github_summary.archive import extract_github_tarball
from app.github_summary.github_client import GitHubClient
from app.github_summary.github_url import parse_github_repository_url
from app.github_summary.settings import GitHubSummarySettings
from app.impact_analysis.domain import RepositoryMappingRecord, RequirementPackage
from app.impact_analysis.enums import AnalysisStage
from app.impact_analysis.repositories.snapshots import SnapshotRepository
from app.impact_analysis.services.source_indexer import SourceIndexer


SCANNER_VERSION = "impact-source-v1"
ProgressCallback = Callable[[AnalysisStage, int, str], None]


class SnapshotService:
    def __init__(
        self,
        *,
        repository: SnapshotRepository | None = None,
        indexer: SourceIndexer | None = None,
        settings: GitHubSummarySettings | None = None,
    ) -> None:
        self.settings = settings or GitHubSummarySettings()
        self.repository = repository or SnapshotRepository()
        self.indexer = indexer or SourceIndexer(settings=self.settings)

    async def create(
        self,
        *,
        package: RequirementPackage,
        requested_ref: str | None,
        force_refresh: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        return await self.create_for_repository(
            repository=package.repository,
            product_space_id=package.project.product_space_id,
            project_id=package.project.project_id,
            requested_ref=requested_ref,
            force_refresh=force_refresh,
            progress_callback=progress_callback,
        )

    async def create_for_repository(
        self,
        *,
        repository: RepositoryMappingRecord,
        product_space_id: UUID,
        project_id: UUID,
        requested_ref: str | None,
        force_refresh: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        repository_ref = parse_github_repository_url(
            repository.repository_url,
            allowed_hosts=self.settings.allowed_hosts,
        )
        async with GitHubClient(self.settings) as github:
            metadata = await github.get_repository(repository_ref)
            branch = requested_ref or repository.default_branch or metadata.default_branch
            commit_sha = await github.get_commit_sha(repository_ref, branch)
            if not commit_sha:
                raise RuntimeError("GitHub did not resolve an immutable commit SHA.")
            if not force_refresh:
                existing = self.repository.find_completed(
                    project_repository_id=repository.project_repository_id,
                    commit_sha=commit_sha,
                    scanner_version=SCANNER_VERSION,
                )
                if existing:
                    if progress_callback is not None:
                        progress_callback(
                            AnalysisStage.SOURCE_INDEXING,
                            48,
                            "Using cached repository source index",
                        )
                    return {**existing, "branch": branch, "cache_hit": True}
            snapshot_id = self.repository.create(
                project_repository_id=repository.project_repository_id,
                repository_id=repository.repository_id,
                product_space_id=product_space_id,
                project_id=project_id,
                branch=branch,
                commit_sha=commit_sha,
                scanner_version=SCANNER_VERSION,
            )
            try:
                archive = await github.download_archive(repository_ref, branch)
                self.repository.set_status(snapshot_id, "SCANNING")
                if progress_callback is not None:
                    progress_callback(
                        AnalysisStage.SOURCE_PARSING,
                        40,
                        "Parsing repository source files",
                    )
                with tempfile.TemporaryDirectory(prefix="impact-source-") as temporary:
                    root = extract_github_tarball(
                        archive,
                        Path(temporary),
                        max_extracted_bytes=self.settings.max_extracted_bytes,
                    )
                    result = self.indexer.index_root(
                        snapshot_id=snapshot_id,
                        root=root,
                        before_persist=(
                            lambda: progress_callback(
                                AnalysisStage.SOURCE_INDEXING,
                                48,
                                "Indexing source symbols and relationships",
                            )
                            if progress_callback is not None
                            else None
                        ),
                    )
                manifest = [
                    {
                        "path": item.path,
                        "content_sha256": item.content_sha256,
                        "language": item.language,
                        "line_count": item.line_count,
                        "parser_status": item.parser_status,
                    }
                    for item in result.parsed_files
                ]
                completed = self.repository.set_status(
                    snapshot_id,
                    "COMPLETED",
                    manifest=manifest,
                    discovered_files=result.discovered_files,
                    indexed_files=result.indexed_files,
                    skipped_files=result.skipped_files,
                    coverage_percent=result.coverage_percent,
                )
            except Exception as error:
                self.repository.set_status(
                    snapshot_id,
                    "FAILED",
                    error_code="SNAPSHOT_FAILED",
                    error_message=str(error)[:2000],
                )
                raise
        return {
            **(completed or {}),
            "id": snapshot_id,
            "project_repository_id": repository.project_repository_id,
            "repository_id": repository.repository_id,
            "product_space_id": product_space_id,
            "project_id": project_id,
            "branch": branch,
            "commit_sha": commit_sha,
            "status": "COMPLETED",
            "scanner_version": SCANNER_VERSION,
            "manifest": manifest,
            "discovered_files": result.discovered_files,
            "indexed_files": result.indexed_files,
            "skipped_files": result.skipped_files,
            "coverage_percent": result.coverage_percent,
            "cache_hit": False,
        }
