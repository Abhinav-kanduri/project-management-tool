import io
import tarfile
from pathlib import Path

import pytest

from app.services.archive import UnsafeArchiveError, extract_github_tarball


def create_tar(name: str, content: bytes = b"hello") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name=name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_extract_archive(tmp_path: Path):
    archive = create_tar("owner-repo-sha/README.md")
    root = extract_github_tarball(archive, tmp_path)
    assert (root / "README.md").read_text() == "hello"


def test_reject_path_traversal(tmp_path: Path):
    archive = create_tar("../outside.txt")
    with pytest.raises(UnsafeArchiveError):
        extract_github_tarball(archive, tmp_path)
