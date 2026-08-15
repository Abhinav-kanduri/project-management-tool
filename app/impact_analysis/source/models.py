from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.impact_analysis.schemas import StrictModel


class SourceSymbol(StrictModel):
    symbol_key: str
    kind: str
    name: str
    qualified_name: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    signature: str | None = None
    visibility: str | None = None
    is_async: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceEdge(StrictModel):
    edge_key: str
    edge_type: str
    from_symbol_key: str | None = None
    to_symbol_key: str | None = None
    target_text: str | None = None
    detection_source: str = "PARSER"
    confidence: float = Field(default=1, ge=0, le=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedSourceFile(StrictModel):
    path: str
    language: str
    content: str
    content_sha256: str
    size_bytes: int = Field(ge=0)
    line_count: int = Field(ge=0)
    is_generated: bool = False
    is_test: bool = False
    parser_name: str
    parser_version: str
    parser_status: str
    symbols: list[SourceSymbol] = Field(default_factory=list)
    edges: list[SourceEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceChunk(StrictModel):
    id: UUID
    snapshot_id: UUID
    file_id: UUID
    symbol_id: UUID | None = None
    chunk_key: str
    chunk_type: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    content_sha256: str
    token_count: int = Field(gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
