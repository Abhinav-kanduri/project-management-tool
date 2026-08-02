from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import Settings
from app.schemas import (
    AnalysisStatistics,
    RepositoryIdentity,
    RepositorySummary,
    RepositorySummaryResponse,
)
from app.services.archive import extract_github_tarball
from app.services.cache import SummaryCache
from app.services.github_client import GitHubClient
from app.services.openai_client import OpenAIResponsesClient
from app.services.scanner import RepositoryScanner, RepositorySnapshot, ScannedFile
from app.utils.github_url import parse_github_repository_url


BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files_reviewed": {"type": "array", "items": {"type": "string"}},
        "overview": {"type": "string"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "responsibility": {"type": "string"},
                },
                "required": ["name", "paths", "responsibility"],
                "additionalProperties": False,
            },
        },
        "api_endpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "purpose": {"type": "string"},
                    "source_file": {"type": ["string", "null"]},
                },
                "required": ["method", "path", "purpose", "source_file"],
                "additionalProperties": False,
            },
        },
        "dependencies": {"type": "array", "items": {"type": "string"}},
        "data_and_storage": {"type": "array", "items": {"type": "string"}},
        "processing_flow": {"type": "array", "items": {"type": "string"}},
        "setup_observations": {"type": "array", "items": {"type": "string"}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence_files": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "files_reviewed",
        "overview",
        "components",
        "api_endpoints",
        "dependencies",
        "data_and_storage",
        "processing_flow",
        "setup_observations",
        "strengths",
        "risks",
        "evidence_files",
    ],
    "additionalProperties": False,
}

FINAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "executive_summary": {"type": "string"},
        "problem_statement": {"type": "string"},
        "primary_capabilities": {"type": "array", "items": {"type": "string"}},
        "architecture": {"type": "array", "items": {"type": "string"}},
        "technology_stack": {"type": "array", "items": {"type": "string"}},
        "key_components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "responsibility": {"type": "string"},
                },
                "required": ["name", "paths", "responsibility"],
                "additionalProperties": False,
            },
        },
        "api_endpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "purpose": {"type": "string"},
                    "source_file": {"type": ["string", "null"]},
                },
                "required": ["method", "path", "purpose", "source_file"],
                "additionalProperties": False,
            },
        },
        "data_and_storage": {"type": "array", "items": {"type": "string"}},
        "request_or_processing_flow": {
            "type": "array",
            "items": {"type": "string"},
        },
        "setup_and_run": {"type": "array", "items": {"type": "string"}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "risks_and_gaps": {"type": "array", "items": {"type": "string"}},
        "recommended_next_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "evidence_files": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "executive_summary",
        "problem_statement",
        "primary_capabilities",
        "architecture",
        "technology_stack",
        "key_components",
        "api_endpoints",
        "data_and_storage",
        "request_or_processing_flow",
        "setup_and_run",
        "strengths",
        "risks_and_gaps",
        "recommended_next_steps",
        "evidence_files",
    ],
    "additionalProperties": False,
}


class RepositorySummaryService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._github = GitHubClient(settings)
        self._scanner = RepositoryScanner(settings)
        self._llm = OpenAIResponsesClient(settings)
        self._cache = SummaryCache(settings)

    async def summarize(
        self,
        *,
        repository_url: str,
        branch: str | None,
        force_refresh: bool,
    ) -> RepositorySummaryResponse:
        started = time.perf_counter()
        repository_ref = parse_github_repository_url(
            repository_url,
            allowed_hosts=self._settings.allowed_hosts,
        )
        metadata = await self._github.get_repository(repository_ref)
        analyzed_ref = branch or metadata.default_branch
        commit_sha = await self._github.get_commit_sha(repository_ref, analyzed_ref)
        languages = await self._github.get_languages(repository_ref)

        cache_key = (
            f"v1|{repository_ref.full_name}|{analyzed_ref}|{commit_sha}|"
            f"{self._settings.openai_model}"
        )
        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached:
                cached["analysis"]["cache_hit"] = True
                cached["duration_seconds"] = round(time.perf_counter() - started, 3)
                return RepositorySummaryResponse.model_validate(cached)

        archive = await self._github.download_archive(repository_ref, analyzed_ref)
        with tempfile.TemporaryDirectory(prefix="github-summary-") as temporary:
            extracted_root = extract_github_tarball(archive, Path(temporary))
            snapshot = self._scanner.scan(extracted_root)

        if not snapshot.files:
            raise RuntimeError("No supported repository files were available for analysis")

        batches = self._create_batches(snapshot.files)
        batch_summaries = []
        for index, batch in enumerate(batches, start=1):
            prompt = self._batch_prompt(
                repository_name=metadata.full_name,
                batch=batch,
                batch_number=index,
                total_batches=len(batches),
            )
            result = await self._llm.generate_structured(
                system_prompt=(
                    "You are a senior software architect analyzing a source repository. "
                    "Use only the supplied repository evidence. Be precise, avoid invented "
                    "endpoints or technologies, and cite repository-relative file paths."
                ),
                user_prompt=prompt,
                schema_name="repository_batch_summary",
                json_schema=BATCH_SCHEMA,
            )
            batch_summaries.append(result)

        final_prompt = self._final_prompt(
            metadata=metadata,
            analyzed_ref=analyzed_ref,
            commit_sha=commit_sha,
            languages=languages,
            snapshot=snapshot,
            batch_summaries=batch_summaries,
        )
        final_payload = await self._llm.generate_structured(
            system_prompt=(
                "You are a principal architect producing a factual repository assessment. "
                "Consolidate duplicate findings. State uncertainty through careful wording. "
                "Use only the evidence supplied in the prompt."
            ),
            user_prompt=final_prompt,
            schema_name="repository_summary",
            json_schema=FINAL_SCHEMA,
        )

        try:
            summary = RepositorySummary.model_validate(final_payload)
        except ValidationError as exc:
            raise RuntimeError("Generated summary did not match the API schema") from exc

        repository_identity = RepositoryIdentity(
            owner=repository_ref.owner,
            name=repository_ref.repository,
            full_name=metadata.full_name,
            url=metadata.html_url,
            visibility=metadata.visibility,
            description=metadata.description,
            default_branch=metadata.default_branch,
            analyzed_ref=analyzed_ref,
            commit_sha=commit_sha,
            language_bytes=languages,
            stars=metadata.stargazers_count,
            forks=metadata.forks_count,
            open_issues=metadata.open_issues_count,
            archived=metadata.archived,
        )
        statistics = AnalysisStatistics(
            archive_bytes=len(archive),
            discovered_files=snapshot.discovered_files,
            analyzed_files=snapshot.analyzed_files,
            skipped_files=snapshot.skipped_files,
            analyzed_characters=snapshot.analyzed_characters,
            batches=len(batches),
            cache_hit=False,
        )
        response = RepositorySummaryResponse(
            generated_at=datetime.now(UTC),
            duration_seconds=round(time.perf_counter() - started, 3),
            repository=repository_identity,
            analysis=statistics,
            summary=summary,
            summary_markdown=self._render_markdown(repository_identity, summary),
            model=self._settings.openai_model,
        )
        self._cache.set(cache_key, response.model_dump(mode="json"))
        return response

    def _create_batches(self, files: list[ScannedFile]) -> list[list[ScannedFile]]:
        batches: list[list[ScannedFile]] = []
        current: list[ScannedFile] = []
        current_characters = 0
        for file in files:
            estimated = len(file.content) + sum(map(len, file.outline)) + 500
            if current and (
                current_characters + estimated
                > self._settings.summary_batch_characters
            ):
                batches.append(current)
                current = []
                current_characters = 0
            current.append(file)
            current_characters += estimated
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _batch_prompt(
        *,
        repository_name: str,
        batch: list[ScannedFile],
        batch_number: int,
        total_batches: int,
    ) -> str:
        parts = [
            f"Repository: {repository_name}",
            f"Evidence batch: {batch_number} of {total_batches}",
            "Analyze the following files. Extract concrete architecture, components, APIs, "
            "dependencies, storage, processing flow, setup details, strengths, and risks.",
        ]
        for file in batch:
            outline = "\n".join(file.outline) if file.outline else "(none detected)"
            parts.append(
                "\n--- FILE START ---\n"
                f"Path: {file.path}\n"
                f"Language: {file.language}\n"
                f"Lines: {file.line_count}\n"
                f"Outline:\n{outline}\n"
                f"Content:\n{file.content}\n"
                "--- FILE END ---"
            )
        return "\n".join(parts)

    @staticmethod
    def _final_prompt(
        *,
        metadata: Any,
        analyzed_ref: str,
        commit_sha: str | None,
        languages: dict[str, int],
        snapshot: RepositorySnapshot,
        batch_summaries: list[dict[str, Any]],
    ) -> str:
        return (
            f"Repository: {metadata.full_name}\n"
            f"Description: {metadata.description or '(none)'}\n"
            f"Analyzed ref: {analyzed_ref}\n"
            f"Commit SHA: {commit_sha or '(unknown)'}\n"
            f"Language bytes: {json.dumps(languages, sort_keys=True)}\n"
            f"Discovered files: {snapshot.discovered_files}\n"
            f"Analyzed files: {snapshot.analyzed_files}\n"
            f"Repository tree: {json.dumps(snapshot.tree[:600])}\n\n"
            "Consolidate the following evidence-batch summaries into one comprehensive, "
            "non-repetitive repository summary. Recommended next steps should be specific "
            "and prioritized. Do not claim that planned documentation is implemented unless "
            "the code evidence supports it.\n\n"
            f"Batch summaries:\n{json.dumps(batch_summaries, indent=2)}"
        )

    @staticmethod
    def _render_markdown(
        repository: RepositoryIdentity,
        summary: RepositorySummary,
    ) -> str:
        lines = [
            f"# {summary.title}",
            "",
            f"**Repository:** [{repository.full_name}]({repository.url})  ",
            f"**Analyzed ref:** `{repository.analyzed_ref}`  ",
            f"**Commit:** `{repository.commit_sha or 'unknown'}`",
            "",
            "## Executive Summary",
            "",
            summary.executive_summary,
            "",
            "## Problem Statement",
            "",
            summary.problem_statement,
        ]
        sections = [
            ("Primary Capabilities", summary.primary_capabilities),
            ("Architecture", summary.architecture),
            ("Technology Stack", summary.technology_stack),
            ("Data and Storage", summary.data_and_storage),
            ("Request / Processing Flow", summary.request_or_processing_flow),
            ("Setup and Run", summary.setup_and_run),
            ("Strengths", summary.strengths),
            ("Risks and Gaps", summary.risks_and_gaps),
            ("Recommended Next Steps", summary.recommended_next_steps),
            ("Evidence Files", [f"`{item}`" for item in summary.evidence_files]),
        ]
        for title, items in sections:
            lines.extend(["", f"## {title}", ""])
            lines.extend(f"- {item}" for item in items)

        lines.extend(["", "## Key Components", ""])
        for component in summary.key_components:
            paths = ", ".join(f"`{path}`" for path in component.paths)
            lines.append(f"- **{component.name}:** {component.responsibility} ({paths})")

        lines.extend(["", "## API Endpoints", ""])
        if summary.api_endpoints:
            lines.extend(
                f"- `{endpoint.method.upper()} {endpoint.path}` — {endpoint.purpose}"
                + (f" (`{endpoint.source_file}`)" if endpoint.source_file else "")
                for endpoint in summary.api_endpoints
            )
        else:
            lines.append("- No confirmed API endpoints found in the analyzed evidence.")
        return "\n".join(lines).strip() + "\n"
