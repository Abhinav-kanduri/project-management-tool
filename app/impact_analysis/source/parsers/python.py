from __future__ import annotations

import ast
from dataclasses import dataclass

from app.impact_analysis.source.models import ParsedSourceFile, SourceEdge, SourceSymbol
from app.impact_analysis.source.parsers.base import parsed_file


@dataclass
class _Context:
    path: str
    parents: list[str]

    def qualified(self, name: str) -> str:
        module = self.path.removesuffix(".py").replace("/", ".")
        return ".".join([module, *self.parents, name])


class PythonSourceParser:
    name = "python-ast"

    def parse(self, *, path: str, content: str, language: str) -> ParsedSourceFile:
        try:
            tree = ast.parse(content)
        except SyntaxError as error:
            return parsed_file(
                path=path,
                content=content,
                language=language,
                parser_name=self.name,
                parser_status="FAILED",
                metadata={"error": str(error)},
            )
        symbols: list[SourceSymbol] = []
        edges: list[SourceEdge] = []
        self._visit_body(tree.body, _Context(path, []), symbols, edges)
        return parsed_file(
            path=path,
            content=content,
            language=language,
            parser_name=self.name,
            parser_status="PARSED",
            symbols=symbols,
            edges=edges,
        )

    def _visit_body(self, body, context, symbols, edges) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                key = context.qualified(node.name)
                kind = "SERVICE" if node.name.endswith(("Service", "Repository")) else "CLASS"
                symbols.append(
                    SourceSymbol(
                        symbol_key=key,
                        kind=kind,
                        name=node.name,
                        qualified_name=key,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        signature=self._class_signature(node),
                        visibility=self._visibility(node.name),
                    )
                )
                child = _Context(context.path, [*context.parents, node.name])
                self._visit_body(node.body, child, symbols, edges)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function(node, context, symbols, edges)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                target = self._import_target(node)
                edges.append(
                    SourceEdge(
                        edge_key=f"{context.path}:IMPORTS:{node.lineno}:{target}",
                        edge_type="IMPORTS",
                        target_text=target,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                    )
                )

    def _function(self, node, context, symbols, edges) -> None:
        key = context.qualified(node.name)
        api = self._api_metadata(node)
        is_test = node.name.startswith("test_") or "/tests/" in f"/{context.path.casefold()}"
        kind = "API" if api else ("TEST" if is_test else ("METHOD" if context.parents else "FUNCTION"))
        symbols.append(
            SourceSymbol(
                symbol_key=key,
                kind=kind,
                name=node.name,
                qualified_name=key,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=self._function_signature(node),
                visibility=self._visibility(node.name),
                is_async=isinstance(node, ast.AsyncFunctionDef),
                metadata={"api": api} if api else {},
            )
        )
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                target = self._expression_name(child.func)
                if target:
                    edges.append(
                        SourceEdge(
                            edge_key=f"{key}:CALLS:{child.lineno}:{target}",
                            edge_type="CALLS",
                            from_symbol_key=key,
                            target_text=target,
                            start_line=child.lineno,
                            end_line=child.end_lineno or child.lineno,
                            confidence=0.75,
                        )
                    )

    @staticmethod
    def _api_metadata(node) -> list[dict[str, str]]:
        endpoints = []
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            name = PythonSourceParser._expression_name(decorator.func)
            method = name.rsplit(".", 1)[-1].upper() if name else ""
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                continue
            path = ""
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = str(decorator.args[0].value)
            endpoints.append({"method": method, "path": path, "decorator": name})
        return endpoints

    @staticmethod
    def _expression_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = PythonSourceParser._expression_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    @staticmethod
    def _import_target(node) -> str:
        if isinstance(node, ast.Import):
            return ",".join(alias.name for alias in node.names)
        names = ",".join(alias.name for alias in node.names)
        return f"{node.module or ''}:{names}"

    @staticmethod
    def _function_signature(node) -> str:
        arguments = [argument.arg for argument in [*node.args.posonlyargs, *node.args.args]]
        if node.args.vararg:
            arguments.append(f"*{node.args.vararg.arg}")
        arguments.extend(argument.arg for argument in node.args.kwonlyargs)
        if node.args.kwarg:
            arguments.append(f"**{node.args.kwarg.arg}")
        return f"{node.name}({', '.join(arguments)})"

    @staticmethod
    def _class_signature(node) -> str:
        bases = [PythonSourceParser._expression_name(base) for base in node.bases]
        return f"class {node.name}({', '.join(item for item in bases if item)})"

    @staticmethod
    def _visibility(name: str) -> str:
        return "PRIVATE" if name.startswith("_") else "PUBLIC"
