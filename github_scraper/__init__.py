from __future__ import annotations

import io
import tarfile
from pathlib import Path


class UnsafeArchiveError(RuntimeError):
    pass


def _is_within_directory(directory: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def extract_github_tarball(archive_bytes: bytes, destination: Path) -> Path:
    """Safely extract a GitHub tarball and return its repository root."""

    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            target = destination / member.name
            if not _is_within_directory(destination, target):
                raise UnsafeArchiveError("Archive contains an unsafe path")
            if member.issym() or member.islnk():
                raise UnsafeArchiveError("Archive links are not accepted")
        archive.extractall(destination, members=members, filter="data")

    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) == 1:
        return roots[0]
    return destination
