import re

from app.impact_analysis.source.models import SourceSymbol
from app.impact_analysis.source.parsers.base import parsed_file


DDL = re.compile(
    r"(?im)^\s*(create|alter)\s+(?:or\s+replace\s+)?(?:table|view|function|procedure|index|extension|schema)\s+(?:if\s+not\s+exists\s+)?([\w.\"-]+)"
)


class SQLSourceParser:
    name = "sql-ddl"

    def parse(self, *, path: str, content: str, language: str):
        symbols = []
        lines = content.splitlines()
        for match in DDL.finditer(content):
            line = content.count("\n", 0, match.start()) + 1
            name = match.group(2).strip('"')
            symbols.append(
                SourceSymbol(
                    symbol_key=f"{path}:database:{name}:{line}",
                    kind="DATABASE_OBJECT",
                    name=name,
                    qualified_name=name,
                    start_line=line,
                    end_line=min(len(lines) or 1, line + 20),
                    signature=match.group(0).strip(),
                )
            )
        return parsed_file(
            path=path,
            content=content,
            language=language,
            parser_name=self.name,
            parser_status="PARSED" if symbols else "PARTIAL",
            symbols=symbols,
        )
