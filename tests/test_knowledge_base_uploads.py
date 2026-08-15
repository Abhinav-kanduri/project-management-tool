from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from fastapi import HTTPException
from starlette.datastructures import Headers

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@localhost:5432/test"
)

from app.services import knowledge_base


def test_persist_upload_uses_project_relative_absolute_root(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / "project"
    server_cwd = tmp_path / "server-cwd"
    project_root.mkdir()
    server_cwd.mkdir()
    monkeypatch.setattr(knowledge_base, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_UPLOAD_ROOT", "data/uploads")
    monkeypatch.chdir(server_cwd)

    product_space_id = uuid4()
    project_id = uuid4()
    original_filename = f"{'repository-summary-' * 8}architecture.md"
    upload = UploadFile(
        filename=original_filename,
        file=io.BytesIO(b"# Architecture"),
        headers=Headers({"content-type": "text/markdown"}),
    )

    (
        document_id,
        stored_path,
        returned_filename,
        size,
        checksum,
        content_type,
    ) = asyncio.run(
        knowledge_base.persist_upload(upload, product_space_id, project_id)
    )

    assert stored_path.is_absolute()
    assert stored_path.is_relative_to(project_root / "data" / "uploads")
    assert stored_path.parent.name == document_id
    assert stored_path.name == "source.md"
    assert returned_filename == original_filename
    assert len(str(stored_path)) < len(str(stored_path.parent / original_filename))
    assert stored_path.read_bytes() == b"# Architecture"
    assert size == len(b"# Architecture")
    assert len(checksum) == 64
    assert content_type == "text/markdown"


def test_persist_upload_returns_structured_storage_error(
    tmp_path: Path, monkeypatch
) -> None:
    blocked_root = tmp_path / "blocked"
    blocked_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_UPLOAD_ROOT", blocked_root)
    upload = UploadFile(
        filename="architecture.md",
        file=io.BytesIO(b"# Architecture"),
        headers=Headers({"content-type": "text/markdown"}),
    )

    try:
        asyncio.run(
            knowledge_base.persist_upload(upload, uuid4(), uuid4())
        )
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail["code"] == "UPLOAD_STORAGE_UNAVAILABLE"
        assert exc.detail["retryable"] is True
    else:
        raise AssertionError("Expected upload storage failure")
