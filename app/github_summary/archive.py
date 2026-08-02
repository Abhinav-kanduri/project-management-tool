from __future__ import annotations

import io
import tarfile
from pathlib import Path, PurePosixPath


class UnsafeArchiveError(RuntimeError):
    pass


def extract_github_tarball(
    archive_bytes: bytes,
    destination: Path,
    *,
    max_extracted_bytes: int,
) -> Path:
    """Extract regular files without trusting tar paths or link metadata."""

    destination.mkdir(parents=True, exist_ok=True)
    extracted_bytes = 0
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise UnsafeArchiveError("Archive contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev():
                raise UnsafeArchiveError("Archive links and device files are not accepted")
            if not (member.isdir() or member.isfile()):
                continue

            target = destination.joinpath(*relative.parts)
            try:
                target.resolve().relative_to(destination.resolve())
            except ValueError as exc:
                raise UnsafeArchiveError("Archive contains an unsafe path") from exc

            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            extracted_bytes += member.size
            if extracted_bytes > max_extracted_bytes:
                raise UnsafeArchiveError("Archive exceeds the extracted-size limit")
            source = archive.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)

    roots = [path for path in destination.iterdir() if path.is_dir()]
    return roots[0] if len(roots) == 1 else destination

