from app.impact_analysis.source.parsers.base import parsed_file


class GenericSourceParser:
    name = "generic-text"

    def parse(self, *, path: str, content: str, language: str):
        return parsed_file(
            path=path,
            content=content,
            language=language,
            parser_name=self.name,
            parser_status="UNSUPPORTED",
            metadata={"coverage": "TEXT_ONLY"},
        )
