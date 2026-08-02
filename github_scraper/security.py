from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings
from app.utils.security import is_sensitive_path, redact_secrets


IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
    "target",
    "bin",
    "obj",
    "__pycache__",
}

TEXT_FILE_NAMES = {
    "dockerfile",
    "makefile",
    "procfile",
    "gemfile",
    "rakefile",
    "license",
    "readme",
}

EXTENSION_LANGUAGE = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript React",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".rb": "Ruby",
    ".php": "PHP",
    ".scala": "Scala",
    ".swift": "Swift",
    ".sql": "SQL",
    ".md": "Markdown",
    ".mdx": "MDX",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".json": "JSON",
    ".jsonc": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "Configuration",
    ".conf": "Configuration",
    ".properties": "Properties",
    ".xml": "XML",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".tf": "Terraform",
    ".tfvars": "Terraform",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".ipynb": "Jupyter Notebook",
}

ENTRYPOINT_NAMES = {
    "main.py",
    "app.py",
    "server.py",
    "index.py",
    "index.js",
    "index.ts",
    "server.js",
    "server.ts",
    "main.go",
    "main.rs",
    "program.cs",
}

CONFIG_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "cargo.toml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "dockerfile",
    "makefile",
    "procfile",
}


@dataclass
class ScannedFile:
    path: str
    language: str
    size_bytes: int
    line_count: int
    content: str
    outline: list[str] = field(default_factory=list)
    importance: int = 0


@dataclass
class RepositorySnapshot:
    discovered_files: int
    analyzed_files: int
    skipped_files: int
    analyzed_characters: int
    files: list[ScannedFile]
    tree: list[str]


class RepositoryScanner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def scan(self, root: Path) -> RepositorySnapshot:
        candidates: list[Path] = []
        discovered = 0
        skipped = 0

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            discovered += 1
            relative = path.relative_to(root)
            relative_text = relative.as_posix()

            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                skipped += 1
                continue
            if is_sensitive_path(relative_text):
                skipped += 1
                continue
            if not self._is_supported(path):
                skipped += 1
                continue
            if path.stat().st_size > self._settings.max_file_bytes:
                skipped += 1
                continue
            candidates.append(path)

        candidates.sort(key=lambda item: item.relative_to(root).as_posix())
        if len(candidates) > self._settings.max_scanned_files:
            skipped += len(candidates) - self._settings.max_scanned_files
            candidates = candidates[: self._settings.max_scanned_files]

        scanned: list[ScannedFile] = []
        for path in candidates:
            relative = path.relative_to(root).as_posix()
            text = self._read_text(path)
            if text is None:
                skipped += 1
                continue
            text = redact_secrets(text)
            language = self._language_for(path)
            scanned.append(
                ScannedFile(
                    path=relative,
                    language=language,
                    size_bytes=path.stat().st_size,
                    line_count=text.count("\n") + 1,
                    content=text,
                    outline=self._extract_outline(text, language),
                    importance=self._importance(relative),
                )
            )

        selected = self._select_summary_files(scanned)
        return RepositorySnapshot(
            discovered_files=discovered,
            analyzed_files=len(selected),
            skipped_files=skipped + max(0, len(scanned) - len(selected)),
            analyzed_characters=sum(len(item.content) for item in selected),
            files=selected,
            tree=[item.path for item in scanned],
        )

    def _is_supported(self, path: Path) -> bool:
        if path.suffix.lower() in EXTENSION_LANGUAGE:
            return True
        return path.name.lower() in TEXT_FILE_NAMES | CONFIG_NAMES

    @staticmethod
    def _read_text(path: Path) -> str | None:
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            return None
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return None

    @staticmethod
    def _language_for(path: Path) -> str:
        name = path.name.lower()
        if name == "dockerfile":
            return "Dockerfile"
        if name == "makefile":
            return "Makefile"
        return EXTENSION_LANGUAGE.get(path.suffix.lower(), "Text")

    @staticmethod
    def _importance(relative_path: str) -> int:
        path = relative_path.lower()
        name = path.rsplit("/", 1)[-1]
        score = 10
        if name.startswith("readme"):
            score += 120
        if name in CONFIG_NAMES:
            score += 100
        if name in ENTRYPOINT_NAMES:
            score += 100
        if path.startswith("docs/") or "/docs/" in path:
            score += 55
        if any(token in path for token in ("architecture", "setup", "deploy", "api")):
            score += 65
        if any(token in path for token in ("route", "controller", "endpoint")):
            score += 60
        if any(token in path for token in ("service", "orchestrator", "agent", "workflow")):
            score += 50
        if any(token in path for token in ("model", "schema", "database", "migration")):
            score += 45
        if any(token in path for token in ("test", "spec")):
            score += 20
        if name.endswith((".lock", ".min.js", ".map")):
            score -= 100
        return score

    def _select_summary_files(self, files: list[ScannedFile]) -> list[ScannedFile]:
        ordered = sorted(files, key=lambda item: (-item.importance, item.path))
        selected: list[ScannedFile] = []
        total = 0
        for item in ordered:
            if len(selected) >= self._settings.max_summary_files:
                break
            allowed = min(len(item.content), self._settings.max_file_characters)
            if selected and total + allowed > self._settings.max_total_summary_characters:
                continue
            item.content = item.content[:allowed]
            selected.append(item)
            total += allowed
        return selected

    @staticmethod
    def _extract_outline(content: str, language: str) -> list[str]:
        if language == "Python":
            return RepositoryScanner._python_outline(content)
        if language == "Markdown":
            return [
                line.strip()
                for line in content.splitlines()
                if re.match(r"^#{1,6}\s+", line)
            ][:80]
        if language == "JSON":
            try:
                payload = json.loads(content)
                if isinstance(payload, dict):
                    return [f"top-level key: {key}" for key in list(payload)[:80]]
            except json.JSONDecodeError:
                pass
        patterns = [
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
            r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)",
            r"^\s*(?:public|private|protected|static|async|final|abstract|synchronized|override|virtual|internal|sealed|partial|\s)+\s*[\w<>,\[\]?]+\s+([A-Za-z_$][\w$]*)\s*\(",
            r"^\s*(?:CREATE|ALTER)\s+(?:TABLE|VIEW|FUNCTION|PROCEDURE|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]-]+)",
        ]
        outline: list[str] = []
        for line in content.splitlines():
            for pattern in patterns:
                match = re.search(pattern, line, flags=re.IGNORECASE)
                if match:
                    outline.append(line.strip()[:240])
                    break
            if len(outline) >= 80:
                break
        return outline

    @staticmethod
    def _python_outline(content: str) -> list[str]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []
        outline: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                outline.append(f"class {node.name} (line {node.lineno})")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                outline.append(f"{prefix} {node.name} (line {node.lineno})")
            if len(outline) >= 80:
                break
        return outline
