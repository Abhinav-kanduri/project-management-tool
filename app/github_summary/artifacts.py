from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import PROJECT_ROOT
from app.github_summary.errors import SummaryArtifactError
from app.github_summary.indexing_models import ArtifactManifest, MarkdownChunk


SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


@dataclass(frozen=True)
class ArtifactPaths:
    directory: Path
    markdown: Path
    chunks: Path
    manifest: Path


class ArtifactStore:
    def __init__(self, output_directory: Path) -> None:
        root = output_directory
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        self.root = root.resolve()

    def paths(self, owner: str, repository: str, commit_sha: str) -> ArtifactPaths:
        if not SAFE_COMPONENT.fullmatch(owner) or not SAFE_COMPONENT.fullmatch(repository):
            raise SummaryArtifactError("Repository identity is unsafe for artifact storage")
        if not COMMIT_SHA.fullmatch(commit_sha):
            raise SummaryArtifactError("Commit SHA is unsafe for artifact storage")
        directory = (self.root / owner / repository / commit_sha.lower()).resolve()
        self._require_within_root(directory)
        return ArtifactPaths(
            directory=directory,
            markdown=directory / "summary.md",
            chunks=directory / "summary.chunks.jsonl",
            manifest=directory / "summary.manifest.json",
        )

    def write_markdown(self, path: Path, markdown: str) -> str:
        self._atomic_write(path, markdown.encode("utf-8"))
        return hashlib.sha256(markdown.encode("utf-8")).hexdigest()

    def write_chunks(self, path: Path, chunks: list[MarkdownChunk]) -> None:
        lines = [
            json.dumps(chunk.model_dump(mode="json"), separators=(",", ":"))
            for chunk in chunks
        ]
        payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        self._atomic_write(path, payload)

    def write_manifest(self, path: Path, manifest: ArtifactManifest) -> None:
        payload = json.dumps(
            manifest.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode("utf-8")
        self._atomic_write(path, payload + b"\n")

    def relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        self._require_within_root(resolved)
        try:
            return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
        except ValueError:
            return resolved.as_posix()

    def resolve_stored_path(self, stored_path: str) -> Path:
        candidate = Path(stored_path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        resolved = candidate.resolve()
        self._require_within_root(resolved)
        return resolved

    def ensure_available(self) -> bool:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            return self.root.is_dir() and os.access(self.root, os.W_OK)
        except OSError:
            return False

    def _atomic_write(self, path: Path, payload: bytes) -> None:
        resolved = path.resolve()
        self._require_within_root(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=resolved.parent,
                prefix=f".{resolved.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(resolved)
        except OSError as exc:
            raise SummaryArtifactError(f"Could not write artifact {resolved.name}") from exc
        finally:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)

    def _require_within_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise SummaryArtifactError("Artifact path escaped the configured directory") from exc

