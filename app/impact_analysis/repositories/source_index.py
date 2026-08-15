from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID, uuid5

from psycopg.types.json import Jsonb

from app.database import get_connection
from app.github_summary.persistence import vector_literal
from app.impact_analysis.source.chunker import CodeAwareChunker
from app.impact_analysis.source.models import ParsedSourceFile


FILE_NAMESPACE = UUID("aa14f52e-9fc5-48a3-82a4-c1764625892c")
SYMBOL_NAMESPACE = UUID("81479280-4e60-440a-bd26-3c9bf777930a")


class SourceIndexRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def replace(self, snapshot_id: UUID, files: list[ParsedSourceFile]) -> dict[str, int]:
        chunker = CodeAwareChunker()
        counts = {"files": 0, "symbols": 0, "edges": 0, "chunks": 0}
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("delete from repository_source_files where snapshot_id=%s", (snapshot_id,))
            for source in files:
                file_id = uuid5(FILE_NAMESPACE, f"{snapshot_id}:{source.path}")
                cursor.execute(
                    """
                    insert into repository_source_files(
                        id,snapshot_id,path,language,content_sha256,size_bytes,
                        line_count,is_generated,is_test,parser_name,parser_version,
                        parser_status,metadata
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        file_id,
                        snapshot_id,
                        source.path,
                        source.language,
                        source.content_sha256,
                        source.size_bytes,
                        source.line_count,
                        source.is_generated,
                        source.is_test,
                        source.parser_name,
                        source.parser_version,
                        source.parser_status,
                        Jsonb(source.metadata),
                    ),
                )
                counts["files"] += 1
                symbol_ids: dict[str, UUID] = {}
                for symbol in source.symbols:
                    symbol_id = uuid5(
                        SYMBOL_NAMESPACE, f"{snapshot_id}:{symbol.symbol_key}"
                    )
                    symbol_ids[symbol.symbol_key] = symbol_id
                    cursor.execute(
                        """
                        insert into repository_source_symbols(
                            id,snapshot_id,file_id,symbol_key,kind,name,
                            qualified_name,start_line,end_line,signature,
                            visibility,is_async,metadata
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            symbol_id,
                            snapshot_id,
                            file_id,
                            symbol.symbol_key,
                            symbol.kind,
                            symbol.name,
                            symbol.qualified_name,
                            symbol.start_line,
                            symbol.end_line,
                            symbol.signature,
                            symbol.visibility,
                            symbol.is_async,
                            Jsonb(symbol.metadata),
                        ),
                    )
                    counts["symbols"] += 1
                for edge in source.edges:
                    cursor.execute(
                        """
                        insert into repository_source_edges(
                            snapshot_id,from_file_id,from_symbol_id,to_symbol_id,
                            edge_type,target_text,detection_source,confidence,
                            start_line,end_line,metadata,edge_key
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        on conflict (snapshot_id,edge_key) do nothing
                        returning id
                        """,
                        (
                            snapshot_id,
                            file_id,
                            symbol_ids.get(edge.from_symbol_key),
                            symbol_ids.get(edge.to_symbol_key),
                            edge.edge_type,
                            edge.target_text,
                            edge.detection_source,
                            edge.confidence,
                            edge.start_line,
                            edge.end_line,
                            Jsonb(edge.metadata),
                            edge.edge_key,
                        ),
                    )
                    if cursor.fetchone() is not None:
                        counts["edges"] += 1
                for chunk in chunker.chunk(
                    snapshot_id=snapshot_id,
                    file_id=file_id,
                    symbol_ids=symbol_ids,
                    source=source,
                ):
                    cursor.execute(
                        """
                        insert into repository_source_chunks(
                            id,snapshot_id,file_id,symbol_id,chunk_key,chunk_type,
                            start_line,end_line,content,content_sha256,token_count,metadata
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            chunk.id,
                            snapshot_id,
                            file_id,
                            chunk.symbol_id,
                            chunk.chunk_key,
                            chunk.chunk_type,
                            chunk.start_line,
                            chunk.end_line,
                            chunk.content,
                            chunk.content_sha256,
                            chunk.token_count,
                            Jsonb(chunk.metadata),
                        ),
                    )
                    counts["chunks"] += 1
            connection.commit()
        return counts

    def structured_search(
        self, *, snapshot_id: UUID, terms: list[str], limit: int = 30
    ) -> list[dict[str, Any]]:
        values = [f"%{term}%" for term in terms if term]
        if not values:
            return []
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select c.id chunk_id,c.snapshot_id,f.id file_id,f.path,
                       s.id symbol_id,s.kind,s.name,s.qualified_name,
                       c.start_line,c.end_line,c.content,c.content_sha256
                from repository_source_symbols s
                join repository_source_files f on f.id=s.file_id
                join repository_source_chunks c on c.symbol_id=s.id
                where s.snapshot_id=%s
                  and (s.name ilike any(%s) or s.qualified_name ilike any(%s)
                       or f.path ilike any(%s))
                order by case when s.name ilike any(%s) then 0 else 1 end,
                         f.path,s.start_line
                limit %s
                """,
                (snapshot_id, values, values, values, values, limit),
            )
            return cursor.fetchall()

    def keyword_search(
        self, *, snapshot_id: UUID, query: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select c.id chunk_id,c.snapshot_id,f.id file_id,f.path,
                       s.id symbol_id,s.kind,s.name,s.qualified_name,
                       c.start_line,c.end_line,c.content,c.content_sha256,
                       ts_rank_cd(c.search_vector, plainto_tsquery('english',%s)) score
                from repository_source_chunks c
                join repository_source_files f on f.id=c.file_id
                left join repository_source_symbols s on s.id=c.symbol_id
                where c.snapshot_id=%s
                  and c.search_vector @@ plainto_tsquery('english',%s)
                order by score desc,f.path,c.start_line
                limit %s
                """,
                (query, snapshot_id, query, limit),
            )
            return cursor.fetchall()

    def vector_search(
        self,
        *,
        snapshot_id: UUID,
        query_vector: list[float],
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            vector = vector_literal(query_vector)
            cursor.execute(
                """
                select c.id chunk_id,c.snapshot_id,f.id file_id,f.path,
                       s.id symbol_id,s.kind,s.name,s.qualified_name,
                       c.start_line,c.end_line,c.content,c.content_sha256,
                       greatest(-1.0,least(1.0,1-(c.embedding <=> %s::vector))) score
                from repository_source_chunks c
                join repository_source_files f on f.id=c.file_id
                left join repository_source_symbols s on s.id=c.symbol_id
                where c.snapshot_id=%s and c.embedding is not null
                order by c.embedding <=> %s::vector
                limit %s
                """,
                (vector, snapshot_id, vector, limit),
            )
            return cursor.fetchall()

    def graph_rows(self, snapshot_id: UUID) -> dict[str, list[dict[str, Any]]]:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select f.*, 'FILE' node_kind from repository_source_files f
                where f.snapshot_id=%s order by f.path
                """,
                (snapshot_id,),
            )
            files = cursor.fetchall()
            cursor.execute(
                """
                select s.*, f.path from repository_source_symbols s
                join repository_source_files f on f.id=s.file_id
                where s.snapshot_id=%s order by f.path,s.start_line
                """,
                (snapshot_id,),
            )
            symbols = cursor.fetchall()
            cursor.execute(
                "select * from repository_source_edges where snapshot_id=%s order by edge_key",
                (snapshot_id,),
            )
            edges = cursor.fetchall()
        return {"files": files, "symbols": symbols, "edges": edges}
