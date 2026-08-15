import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from app.impact_analysis.enums import (
    AnalysisStage,
    GraphNodeType,
    GraphRelationshipType,
    RetrievalMethod,
)
from app.impact_analysis.graph.actual_builder import ActualGraphBuilder
from app.impact_analysis.repositories.source_index import SourceIndexRepository
from app.impact_analysis.retrieval.hybrid import HybridRetriever
from app.impact_analysis.retrieval.models import RetrievalCandidate
from app.impact_analysis.retrieval.vector import VectorRetriever
from app.impact_analysis.services.snapshot_service import SnapshotService
from app.impact_analysis.services.source_indexer import SourceIndexResult
from app.impact_analysis.source.chunker import CodeAwareChunker
from app.impact_analysis.source.parsers.python import PythonSourceParser
from app.impact_analysis.source.parsers.registry import SourceParserRegistry


PYTHON_SOURCE = """from fastapi import APIRouter

router = APIRouter()

class ChatService:
    async def process(self, query):
        return await rag.retrieve(query)

@router.post('/chat')
async def chat(payload):
    return await ChatService().process(payload)
"""


def test_python_parser_extracts_service_api_methods_calls_and_spans() -> None:
    parsed = PythonSourceParser().parse(
        path="app/routes/chat.py", content=PYTHON_SOURCE, language="Python"
    )
    by_name = {symbol.name: symbol for symbol in parsed.symbols}
    assert by_name["ChatService"].kind == "SERVICE"
    assert by_name["process"].kind == "METHOD"
    assert by_name["chat"].kind == "API"
    assert by_name["chat"].metadata["api"] == [
        {"method": "POST", "path": "/chat", "decorator": "router.post"}
    ]
    assert by_name["process"].start_line <= by_name["process"].end_line
    assert any(edge.edge_type == "CALLS" and edge.target_text == "rag.retrieve" for edge in parsed.edges)


def test_parser_registry_extracts_sql_dependencies_and_config() -> None:
    registry = SourceParserRegistry()
    sql = registry.parse(
        path="sql/001.sql",
        content="create table if not exists public.items (id uuid);",
        language="SQL",
    )
    requirements = registry.parse(
        path="requirements.txt", content="fastapi==1.0\npsycopg>=3\n", language="Text"
    )
    config = registry.parse(
        path="compose.yaml", content="services:\n  api:\n", language="YAML"
    )
    assert sql.symbols[0].kind == "DATABASE_OBJECT"
    assert {item.name for item in requirements.symbols} == {"fastapi", "psycopg"}
    assert any(item.name == "services" for item in config.symbols)


def test_code_chunks_preserve_exact_symbol_lines() -> None:
    source = PythonSourceParser().parse(
        path="app/routes/chat.py", content=PYTHON_SOURCE, language="Python"
    )
    snapshot_id = uuid4()
    file_id = uuid4()
    symbol_ids = {item.symbol_key: uuid4() for item in source.symbols}
    chunks = CodeAwareChunker(maximum_lines=20).chunk(
        snapshot_id=snapshot_id,
        file_id=file_id,
        symbol_ids=symbol_ids,
        source=source,
    )
    chat = [chunk for chunk in chunks if "chat(" in chunk.content][0]
    lines = PYTHON_SOURCE.splitlines()
    assert chat.content == "\n".join(lines[chat.start_line - 1 : chat.end_line]).strip()
    assert chat.content_sha256


def test_source_index_ignores_duplicate_parser_edges() -> None:
    source = PythonSourceParser().parse(
        path="app/routes/chat.py", content=PYTHON_SOURCE, language="Python"
    )
    duplicate = source.model_copy(
        update={"edges": [source.edges[0], source.edges[0]]}
    )

    class Cursor:
        def __init__(self):
            self.edge_keys = set()
            self.inserted_edge = False
            self.edge_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, parameters=None):
            self.inserted_edge = "insert into repository_source_edges" in statement
            if self.inserted_edge:
                self.edge_sql = statement
                edge_key = parameters[-1]
                self.was_inserted = edge_key not in self.edge_keys
                self.edge_keys.add(edge_key)

        def fetchone(self):
            return {"id": uuid4()} if self.inserted_edge and self.was_inserted else None

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self._cursor

        def commit(self):
            return None

    cursor = Cursor()
    counts = SourceIndexRepository(lambda: Connection(cursor)).replace(
        uuid4(), [duplicate]
    )

    assert counts["edges"] == 1
    assert "on conflict (snapshot_id,edge_key) do nothing" in cursor.edge_sql


def test_hybrid_retrieval_deduplicates_and_records_methods() -> None:
    snapshot_id = uuid4()
    chunk_id = uuid4()
    base = dict(
        candidate_key=f"chunk:{chunk_id}",
        snapshot_id=snapshot_id,
        chunk_id=chunk_id,
        file_path="app/service.py",
        start_line=1,
        end_line=5,
        content="Redis cache",
        rank=1,
    )
    structured = RetrievalCandidate(
        method=RetrievalMethod.STRUCTURED_SYMBOL, **base
    )
    keyword = RetrievalCandidate(method=RetrievalMethod.KEYWORD_FTS, **base)
    result = HybridRetriever().fuse([[structured], [keyword]])
    assert len(result) == 1
    assert result[0].metadata["retrieval_methods"] == [
        "KEYWORD_FTS",
        "STRUCTURED_SYMBOL",
    ]
    assert result[0].fused_score > 0


def test_vector_retrieval_is_disabled_without_explicit_embedding_provider() -> None:
    class Repository:
        def vector_search(self, **kwargs):
            raise AssertionError("Repository must not be called without consented provider")

    assert VectorRetriever(repository=Repository()).search(
        snapshot_id=uuid4(), query="private source"
    ) == []


def test_actual_graph_contains_snapshot_files_symbols_and_calls() -> None:
    run_id = uuid4()
    snapshot_id = uuid4()
    project_id = uuid4()
    file_id = uuid4()
    function_id = uuid4()
    rows = {
        "files": [
            {"id": file_id, "path": "app/service.py", "language": "Python"}
        ],
        "symbols": [
            {
                "id": function_id,
                "file_id": file_id,
                "kind": "FUNCTION",
                "name": "process",
                "qualified_name": "app.service.process",
                "start_line": 1,
                "end_line": 3,
            }
        ],
        "edges": [
            {
                "edge_key": "call-1",
                "edge_type": "CALLS",
                "from_file_id": file_id,
                "from_symbol_id": function_id,
                "to_symbol_id": None,
                "target_text": "redis.get",
                "confidence": 0.75,
            }
        ],
    }
    graph = ActualGraphBuilder().build(
        run_id=run_id,
        snapshot_id=snapshot_id,
        repository_name="example/backend",
        project_id=project_id,
        rows=rows,
    )
    assert GraphNodeType.REPOSITORY_SNAPSHOT in {node.type for node in graph.nodes}
    assert GraphNodeType.FILE in {node.type for node in graph.nodes}
    assert GraphNodeType.FUNCTION in {node.type for node in graph.nodes}
    assert GraphRelationshipType.CALLS in {edge.type for edge in graph.edges}


def test_snapshot_service_pins_sha_and_persists_manifest(
    monkeypatch, requirement_package, tmp_path
) -> None:
    snapshot_id = uuid4()

    class SnapshotRepository:
        def __init__(self):
            self.statuses = []

        def find_completed(self, **kwargs):
            return None

        def create(self, **kwargs):
            assert kwargs["commit_sha"] == "a" * 40
            return snapshot_id

        def set_status(self, snapshot, status, **kwargs):
            self.statuses.append((status, kwargs))

    class Indexer:
        def index_root(self, *, snapshot_id, root, before_persist=None):
            if before_persist:
                before_persist()
            parsed = PythonSourceParser().parse(
                path="app/main.py", content="def main():\n    return 1\n", language="Python"
            )
            return SourceIndexResult(1, 1, 0, [parsed], {"files": 1})

    class GitHub:
        def __init__(self, settings): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get_repository(self, ref):
            return type("Metadata", (), {"default_branch": "main"})()
        async def get_commit_sha(self, ref, branch): return "a" * 40
        async def download_archive(self, ref, branch): return b"archive"

    def extract(archive, destination, **kwargs):
        root = destination / "repository"
        root.mkdir()
        return root

    monkeypatch.setattr(
        "app.impact_analysis.services.snapshot_service.GitHubClient", GitHub
    )
    monkeypatch.setattr(
        "app.impact_analysis.services.snapshot_service.extract_github_tarball", extract
    )
    repository = SnapshotRepository()
    progress = []
    result = asyncio.run(
        SnapshotService(repository=repository, indexer=Indexer()).create(
            package=requirement_package,
            requested_ref="main",
            progress_callback=lambda stage, percent, message: progress.append(
                (stage, percent, message)
            ),
        )
    )
    assert result["commit_sha"] == "a" * 40
    assert result["manifest"][0]["path"] == "app/main.py"
    assert repository.statuses[-1][0] == "COMPLETED"
    assert [item[0] for item in progress] == [
        AnalysisStage.SOURCE_PARSING,
        AnalysisStage.SOURCE_INDEXING,
    ]
