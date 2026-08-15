import re

from app.impact_analysis.source.models import SourceSymbol
from app.impact_analysis.source.parsers.base import parsed_file


KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]")


class ConfigSourceParser:
    name = "configuration"

    def parse(self, *, path: str, content: str, language: str):
        symbols = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            match = KEY.match(line)
            if match:
                name = match.group(1)
                symbols.append(
                    SourceSymbol(
                        symbol_key=f"{path}:config:{name}:{line_number}",
                        kind="CONFIGURATION",
                        name=name,
                        qualified_name=f"{path}:{name}",
                        start_line=line_number,
                        end_line=line_number,
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
