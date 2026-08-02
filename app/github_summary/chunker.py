from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

try:
    import tiktoken
except ImportError:  # pragma: no cover - exercised only in minimal deployments
    tiktoken = None


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_SEPARATOR_PATTERN = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class ChunkDraft:
    heading_path: tuple[str, ...]
    section_title: str | None
    start_line: int
    end_line: int
    token_count: int
    content_sha256: str
    content: str


@dataclass(frozen=True)
class _Block:
    text: str
    start_line: int
    end_line: int
    kind: str


@dataclass(frozen=True)
class _Section:
    heading_path: tuple[str, ...]
    title: str | None
    lines: tuple[tuple[int, str], ...]


class TokenCounter:
    def __init__(self, model: str) -> None:
        self._encoding = None
        if tiktoken is not None:
            try:
                self._encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")

    @property
    def uses_approximation(self) -> bool:
        return self._encoding is None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return max(1, math.ceil(len(text) / 4))

    def split(self, text: str, target: int, overlap: int) -> list[str]:
        if self.count(text) <= target:
            return [text]
        if self._encoding is not None:
            encoded = self._encoding.encode(text)
            step = max(1, target - overlap)
            return [
                self._encoding.decode(encoded[start : start + target]).strip()
                for start in range(0, len(encoded), step)
                if encoded[start : start + target]
            ]
        words = text.split()
        approximate_words = max(1, int(target * 0.72))
        overlap_words = max(0, int(overlap * 0.72))
        step = max(1, approximate_words - overlap_words)
        return [
            " ".join(words[start : start + approximate_words])
            for start in range(0, len(words), step)
            if words[start : start + approximate_words]
        ]


class MarkdownChunker:
    def __init__(
        self,
        *,
        embedding_model: str,
        target_tokens: int = 600,
        overlap_tokens: int = 80,
        min_tokens: int = 80,
    ) -> None:
        if target_tokens < 1:
            raise ValueError("Chunk target must be positive")
        if overlap_tokens < 0 or overlap_tokens >= target_tokens:
            raise ValueError("Chunk overlap must be smaller than the target")
        if min_tokens < 1 or min_tokens > target_tokens:
            raise ValueError("Chunk minimum must be between 1 and the target")
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.min_tokens = min_tokens
        self.tokens = TokenCounter(embedding_model)

    def chunk(self, markdown: str) -> list[ChunkDraft]:
        normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
        sections = self._sections(normalized.splitlines())
        drafts: list[ChunkDraft] = []
        for section in sections:
            drafts.extend(self._chunk_section(section))
        return drafts

    @staticmethod
    def _sections(lines: list[str]) -> list[_Section]:
        sections: list[_Section] = []
        hierarchy: list[str] = []
        current_path: tuple[str, ...] = ()
        current_title: str | None = None
        current_lines: list[tuple[int, str]] = []

        def flush() -> None:
            if current_lines and any(line.strip() for _, line in current_lines):
                sections.append(
                    _Section(current_path, current_title, tuple(current_lines))
                )

        for line_number, line in enumerate(lines, start=1):
            heading = HEADING_PATTERN.match(line)
            if heading:
                flush()
                level = len(heading.group(1))
                title = heading.group(2).strip()
                hierarchy[:] = hierarchy[: level - 1]
                hierarchy.append(title)
                current_path = tuple(hierarchy)
                current_title = title
                current_lines = [(line_number, line)]
            else:
                current_lines.append((line_number, line))
        flush()
        return sections

    def _chunk_section(self, section: _Section) -> list[ChunkDraft]:
        blocks = self._blocks(section.lines)
        expanded: list[_Block] = []
        for block in blocks:
            if block.kind in {"code", "table"} or self.tokens.count(block.text) <= self.target_tokens:
                expanded.append(block)
                continue
            for part in self.tokens.split(
                block.text, self.target_tokens, self.overlap_tokens
            ):
                expanded.append(
                    _Block(part, block.start_line, block.end_line, "paragraph")
                )

        groups: list[list[_Block]] = []
        current: list[_Block] = []
        current_tokens = 0
        for block in expanded:
            block_tokens = self.tokens.count(block.text)
            separator_tokens = 1 if current else 0
            if current and current_tokens + separator_tokens + block_tokens > self.target_tokens:
                groups.append(current)
                current = self._overlap_blocks(current)
                current_tokens = self.tokens.count(self._join(current))
            current.append(block)
            current_tokens = self.tokens.count(self._join(current))
        if current:
            groups.append(current)

        if len(groups) > 1 and self.tokens.count(self._join(groups[-1])) < self.min_tokens:
            candidate = self._deduplicate_blocks(groups[-2] + groups[-1])
            if self.tokens.count(self._join(candidate)) <= self.target_tokens + self.overlap_tokens:
                groups[-2] = candidate
                groups.pop()

        return [self._draft(section, group) for group in groups if self._join(group).strip()]

    def _overlap_blocks(self, blocks: list[_Block]) -> list[_Block]:
        overlap: list[_Block] = []
        tokens = 0
        for block in reversed(blocks):
            if block.kind == "heading":
                continue
            count = self.tokens.count(block.text)
            if overlap and tokens + count > self.overlap_tokens:
                break
            overlap.insert(0, block)
            tokens += count
            if tokens >= self.overlap_tokens:
                break
        return overlap

    @staticmethod
    def _deduplicate_blocks(blocks: list[_Block]) -> list[_Block]:
        result: list[_Block] = []
        seen: set[tuple[int, int, str]] = set()
        for block in blocks:
            identity = (block.start_line, block.end_line, block.text)
            if identity not in seen:
                seen.add(identity)
                result.append(block)
        return result

    @staticmethod
    def _join(blocks: list[_Block]) -> str:
        return "\n\n".join(block.text.strip("\n") for block in blocks).strip()

    def _draft(self, section: _Section, blocks: list[_Block]) -> ChunkDraft:
        content = self._join(blocks)
        return ChunkDraft(
            heading_path=section.heading_path,
            section_title=section.title,
            start_line=min(block.start_line for block in blocks),
            end_line=max(block.end_line for block in blocks),
            token_count=self.tokens.count(content),
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            content=content,
        )

    @staticmethod
    def _blocks(lines: tuple[tuple[int, str], ...]) -> list[_Block]:
        blocks: list[_Block] = []
        index = 0
        while index < len(lines):
            line_number, line = lines[index]
            if not line.strip():
                index += 1
                continue
            if HEADING_PATTERN.match(line):
                blocks.append(_Block(line, line_number, line_number, "heading"))
                index += 1
                continue
            fence = FENCE_PATTERN.match(line)
            if fence:
                marker = fence.group(1)
                collected = [(line_number, line)]
                index += 1
                while index < len(lines):
                    collected.append(lines[index])
                    if lines[index][1].lstrip().startswith(marker):
                        index += 1
                        break
                    index += 1
                blocks.append(
                    _Block(
                        "\n".join(item[1] for item in collected),
                        collected[0][0],
                        collected[-1][0],
                        "code",
                    )
                )
                continue
            if (
                "|" in line
                and index + 1 < len(lines)
                and TABLE_SEPARATOR_PATTERN.match(lines[index + 1][1])
            ):
                collected = [lines[index], lines[index + 1]]
                index += 2
                while index < len(lines) and "|" in lines[index][1] and lines[index][1].strip():
                    collected.append(lines[index])
                    index += 1
                blocks.append(
                    _Block(
                        "\n".join(item[1] for item in collected),
                        collected[0][0],
                        collected[-1][0],
                        "table",
                    )
                )
                continue

            collected = [(line_number, line)]
            index += 1
            while index < len(lines):
                following = lines[index][1]
                if not following.strip() or HEADING_PATTERN.match(following) or FENCE_PATTERN.match(following):
                    break
                if (
                    "|" in following
                    and index + 1 < len(lines)
                    and TABLE_SEPARATOR_PATTERN.match(lines[index + 1][1])
                ):
                    break
                collected.append(lines[index])
                index += 1
            blocks.append(
                _Block(
                    "\n".join(item[1] for item in collected),
                    collected[0][0],
                    collected[-1][0],
                    "paragraph",
                )
            )
        return blocks

