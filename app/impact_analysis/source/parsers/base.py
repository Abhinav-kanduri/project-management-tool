from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from app.impact_analysis.source.models import ParsedSourceFile


PARSER_VERSION = "1"


class SourceParser(Protocol):
    name: str

    def parse(self, *, path: str, content: str, language: str) -> ParsedSourceFile: ...


def parsed_file(
    *,
    path: str,
    content: str,
    language: str,
    parser_name: str,
    parser_status: str,
    symbols=None,
    edges=None,
    metadata=None,
) -> ParsedSourceFile:
    lowered = path.casefold()
    return ParsedSourceFile(
        path=path,
        language=language,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        size_bytes=len(content.encode("utf-8")),
        line_count=content.count("\n") + 1,
        is_generated=any(part in lowered for part in ("generated", ".min.", "vendor/")),
        is_test=(
            Path(path).name.startswith("test_")
            or "/tests/" in f"/{lowered}"
            or lowered.endswith("_test.py")
        ),
        parser_name=parser_name,
        parser_version=PARSER_VERSION,
        parser_status=parser_status,
        symbols=symbols or [],
        edges=edges or [],
        metadata=metadata or {},
    )
