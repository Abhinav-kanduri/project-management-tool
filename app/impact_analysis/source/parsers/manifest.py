import re

from app.impact_analysis.source.models import SourceSymbol
from app.impact_analysis.source.parsers.base import parsed_file


DEPENDENCY = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:\[.*?\])?\s*([<>=!~].*)?$")


class ManifestSourceParser:
    name = "dependency-manifest"

    def parse(self, *, path: str, content: str, language: str):
        symbols = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            value = line.split("#", 1)[0].strip()
            if not value or value.startswith(("-r", "--")):
                continue
            match = DEPENDENCY.match(value)
            if match:
                name = match.group(1)
                symbols.append(
                    SourceSymbol(
                        symbol_key=f"{path}:dependency:{name.casefold()}:{line_number}",
                        kind="DEPENDENCY",
                        name=name,
                        qualified_name=name.casefold(),
                        start_line=line_number,
                        end_line=line_number,
                        signature=value,
                        metadata={"version_specifier": (match.group(2) or "").strip()},
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
