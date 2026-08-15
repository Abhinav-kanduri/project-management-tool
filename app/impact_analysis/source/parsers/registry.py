from pathlib import Path

from app.impact_analysis.source.parsers.config import ConfigSourceParser
from app.impact_analysis.source.parsers.generic import GenericSourceParser
from app.impact_analysis.source.parsers.manifest import ManifestSourceParser
from app.impact_analysis.source.parsers.python import PythonSourceParser
from app.impact_analysis.source.parsers.sql import SQLSourceParser


class SourceParserRegistry:
    def __init__(self) -> None:
        self.python = PythonSourceParser()
        self.sql = SQLSourceParser()
        self.manifest = ManifestSourceParser()
        self.config = ConfigSourceParser()
        self.generic = GenericSourceParser()

    def parser_for(self, path: str, language: str):
        name = Path(path).name.casefold()
        suffix = Path(path).suffix.casefold()
        if language.casefold() == "python" or suffix == ".py":
            return self.python
        if language.casefold() == "sql" or suffix == ".sql":
            return self.sql
        if name in {"requirements.txt", "requirements-dev.txt", "constraints.txt"}:
            return self.manifest
        if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".env"} or name in {
            "dockerfile",
            "compose.yaml",
            "compose.yml",
        }:
            return self.config
        return self.generic

    def parse(self, *, path: str, content: str, language: str):
        return self.parser_for(path, language).parse(
            path=path, content=content, language=language
        )
