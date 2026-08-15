from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

from app.impact_analysis.source.models import ParsedSourceFile, SourceChunk


CHUNK_NAMESPACE = UUID("8c8ab2b8-eef2-43db-851f-fe143d931c65")


class CodeAwareChunker:
    def __init__(self, *, maximum_lines: int = 160, overlap_lines: int = 12) -> None:
        if maximum_lines < 20 or overlap_lines < 0 or overlap_lines >= maximum_lines:
            raise ValueError("Invalid source chunk line limits")
        self.maximum_lines = maximum_lines
        self.overlap_lines = overlap_lines

    def chunk(
        self,
        *,
        snapshot_id: UUID,
        file_id: UUID,
        symbol_ids: dict[str, UUID],
        source: ParsedSourceFile,
    ) -> list[SourceChunk]:
        lines = source.content.splitlines()
        chunks = []
        if source.symbols:
            for symbol in source.symbols:
                chunks.extend(
                    self._ranges(
                        snapshot_id=snapshot_id,
                        file_id=file_id,
                        symbol_id=symbol_ids[symbol.symbol_key],
                        chunk_type=self._chunk_type(symbol.kind),
                        key=symbol.symbol_key,
                        lines=lines,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                    )
                )
        else:
            chunks.extend(
                self._ranges(
                    snapshot_id=snapshot_id,
                    file_id=file_id,
                    symbol_id=None,
                    chunk_type="GENERIC",
                    key=source.path,
                    lines=lines,
                    start_line=1,
                    end_line=max(1, len(lines)),
                )
            )
        return chunks

    def _ranges(self, *, snapshot_id, file_id, symbol_id, chunk_type, key, lines, start_line, end_line):
        result = []
        cursor = start_line
        part = 0
        while cursor <= end_line:
            part_end = min(end_line, cursor + self.maximum_lines - 1)
            content = "\n".join(lines[cursor - 1 : part_end]).strip()
            if content:
                chunk_key = f"{key}:part:{part}:{cursor}-{part_end}"
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                result.append(
                    SourceChunk(
                        id=uuid5(CHUNK_NAMESPACE, f"{snapshot_id}:{chunk_key}"),
                        snapshot_id=snapshot_id,
                        file_id=file_id,
                        symbol_id=symbol_id,
                        chunk_key=chunk_key,
                        chunk_type=chunk_type,
                        start_line=cursor,
                        end_line=part_end,
                        content=content,
                        content_sha256=content_hash,
                        token_count=max(1, len(content.split())),
                    )
                )
            if part_end >= end_line:
                break
            cursor = part_end - self.overlap_lines + 1
            part += 1
        return result

    @staticmethod
    def _chunk_type(kind: str) -> str:
        return {
            "CLASS": "CLASS",
            "SERVICE": "CLASS",
            "FUNCTION": "FUNCTION",
            "METHOD": "METHOD",
            "API": "API",
            "TEST": "TEST",
            "DATABASE_OBJECT": "MIGRATION",
            "CONFIGURATION": "CONFIGURATION",
            "DEPENDENCY": "CONFIGURATION",
        }.get(kind, "GENERIC")
