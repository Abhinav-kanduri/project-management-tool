from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Error as PsycopgError
from psycopg.types.json import Jsonb

from app.database import get_connection
from app.github_summary.errors import SummaryDatabaseError
from app.github_summary.indexing_models import MarkdownChunk


PROCESSING_STATUSES = {
    "SUMMARY_GENERATED",
    "CHUNKING",
    "EMBEDDING",
    "INDEXING",
}


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def serialize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    serialized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, UUID):
            serialized[key] = str(value)
        elif hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


class SummaryRepository:
    def find_completed(
        self,
        *,
        repository_full_name: str,
        branch: str,
        commit_sha: str,
        summary_format_version: str,
        summary_model: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> dict[str, Any] | None:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    select *
                    from github_repository_summary_documents
                    where repository_full_name = %s
                      and branch = %s
                      and commit_sha = %s
                      and summary_format_version = %s
                      and summary_model = %s
                      and embedding_model = %s
                      and embedding_dimensions = %s
                      and status = 'COMPLETED'
                    limit 1
                    """,
                    (
                        repository_full_name,
                        branch,
                        commit_sha,
                        summary_format_version,
                        summary_model,
                        embedding_model,
                        embedding_dimensions,
                    ),
                )
                return serialize_row(cursor.fetchone())
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to read repository summary cache") from exc

    def upsert_generated(
        self,
        *,
        document_id: UUID,
        repository_url: str,
        repository_owner: str,
        repository_name: str,
        repository_full_name: str,
        branch: str,
        commit_sha: str,
        markdown_path: str,
        chunks_path: str,
        manifest_path: str,
        summary_sha256: str,
        summary_format_version: str,
        summary_model: str,
        embedding_model: str,
        embedding_dimensions: int,
        generated_at: datetime,
        response_payload: dict[str, Any],
    ) -> UUID:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into github_repository_summary_documents (
                        id, repository_url, repository_owner, repository_name,
                        repository_full_name, branch, commit_sha, markdown_path,
                        chunks_path, manifest_path, summary_sha256, status,
                        summary_format_version, summary_model, embedding_model,
                        embedding_dimensions, generated_at, response_payload
                    )
                    values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'SUMMARY_GENERATED', %s, %s, %s, %s, %s, %s
                    )
                    on conflict (
                        repository_full_name, branch, commit_sha,
                        summary_format_version, summary_model,
                        embedding_model, embedding_dimensions
                    ) do update set
                        repository_url = excluded.repository_url,
                        repository_owner = excluded.repository_owner,
                        repository_name = excluded.repository_name,
                        markdown_path = excluded.markdown_path,
                        chunks_path = excluded.chunks_path,
                        manifest_path = excluded.manifest_path,
                        summary_sha256 = excluded.summary_sha256,
                        status = 'SUMMARY_GENERATED',
                        chunk_count = 0,
                        error_message = null,
                        generated_at = excluded.generated_at,
                        indexed_at = null,
                        response_payload = excluded.response_payload,
                        updated_at = now()
                    returning id
                    """,
                    (
                        document_id,
                        repository_url,
                        repository_owner,
                        repository_name,
                        repository_full_name,
                        branch,
                        commit_sha,
                        markdown_path,
                        chunks_path,
                        manifest_path,
                        summary_sha256,
                        summary_format_version,
                        summary_model,
                        embedding_model,
                        embedding_dimensions,
                        generated_at,
                        Jsonb(response_payload),
                    ),
                )
                resolved_id = cursor.fetchone()["id"]
                connection.commit()
                return resolved_id
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to create repository summary record") from exc

    def set_status(self, document_id: UUID, status: str) -> None:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    update github_repository_summary_documents
                    set status = %s, updated_at = now()
                    where id = %s
                    """,
                    (status, document_id),
                )
                connection.commit()
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to update repository summary status") from exc

    def replace_chunks_and_complete(
        self,
        *,
        document_id: UUID,
        chunks: list[MarkdownChunk],
        indexed_at: datetime,
        response_payload: dict[str, Any],
    ) -> None:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "delete from github_repository_summary_chunks where document_id = %s",
                    (document_id,),
                )
                for chunk in chunks:
                    if chunk.embedding is None:
                        raise ValueError("Cannot index a chunk without an embedding")
                    metadata = {
                        "repository_url": chunk.repository_url,
                        "repository_full_name": chunk.repository_full_name,
                        "branch": chunk.branch,
                        "commit_sha": chunk.commit_sha,
                        "source_file": chunk.source_file,
                    }
                    cursor.execute(
                        """
                        insert into github_repository_summary_chunks (
                            id, document_id, chunk_index, heading_path,
                            section_title, start_line, end_line, token_count,
                            content_sha256, content, embedding_model,
                            embedding_dimensions, embedding, metadata, created_at
                        )
                        values (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s::vector, %s, %s
                        )
                        """,
                        (
                            chunk.chunk_id,
                            document_id,
                            chunk.chunk_index,
                            Jsonb(chunk.heading_path),
                            chunk.section_title,
                            chunk.start_line,
                            chunk.end_line,
                            chunk.token_count,
                            chunk.content_sha256,
                            chunk.content,
                            chunk.embedding_model,
                            chunk.embedding_dimensions,
                            vector_literal(chunk.embedding),
                            Jsonb(metadata),
                            chunk.created_at,
                        ),
                    )
                cursor.execute(
                    """
                    update github_repository_summary_documents
                    set status = 'COMPLETED',
                        chunk_count = %s,
                        indexed_at = %s,
                        response_payload = %s,
                        error_message = null,
                        updated_at = now()
                    where id = %s
                    """,
                    (len(chunks), indexed_at, Jsonb(response_payload), document_id),
                )
                connection.commit()
        except (PsycopgError, ValueError) as exc:
            raise SummaryDatabaseError("Unable to index repository summary chunks") from exc

    def mark_failed(self, document_id: UUID, error_message: str) -> None:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "delete from github_repository_summary_chunks where document_id = %s",
                    (document_id,),
                )
                cursor.execute(
                    """
                    update github_repository_summary_documents
                    set status = 'FAILED',
                        error_message = %s,
                        indexed_at = null,
                        updated_at = now()
                    where id = %s
                    """,
                    (error_message[:2000], document_id),
                )
                connection.commit()
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to record repository summary failure") from exc

    def get_document(self, document_id: UUID) -> dict[str, Any] | None:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "select * from github_repository_summary_documents where id = %s",
                    (document_id,),
                )
                return serialize_row(cursor.fetchone())
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to load repository summary document") from exc

    def find_latest_completed_for_ref(
        self, *, repository_url: str, branch: str
    ) -> dict[str, Any] | None:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    select id as document_id, repository_url,
                           repository_full_name, branch, commit_sha,
                           coalesce(
                               response_payload->'summary'->>'title',
                               repository_full_name || ' repository summary'
                           ) as title,
                           generated_at, indexed_at, chunk_count
                    from github_repository_summary_documents
                    where repository_url = %s
                      and branch = %s
                      and status = 'COMPLETED'
                    order by indexed_at desc nulls last, generated_at desc
                    limit 1
                    """,
                    (repository_url, branch),
                )
                return serialize_row(cursor.fetchone())
        except PsycopgError as exc:
            raise SummaryDatabaseError(
                "Unable to load the latest repository summary"
            ) from exc

    def list_chunks(
        self, document_id: UUID, *, offset: int, limit: int
    ) -> tuple[int, list[dict[str, Any]]]:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "select count(*)::integer as total from github_repository_summary_chunks where document_id = %s",
                    (document_id,),
                )
                total = cursor.fetchone()["total"]
                cursor.execute(
                    """
                    select id as chunk_id, chunk_index, heading_path,
                           section_title, start_line, end_line, token_count, content
                    from github_repository_summary_chunks
                    where document_id = %s
                    order by chunk_index
                    offset %s limit %s
                    """,
                    (document_id, offset, limit),
                )
                return total, [serialize_row(row) for row in cursor.fetchall()]
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to list repository summary chunks") from exc

    def semantic_search(
        self,
        *,
        query_vector: list[float],
        document_id: UUID | None,
        repository_url: str | None,
        branch: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        filters = ["d.status = 'COMPLETED'"]
        parameters: list[Any] = [vector_literal(query_vector)]
        if document_id:
            filters.append("d.id = %s")
            parameters.append(document_id)
        if repository_url:
            filters.append("d.repository_url = %s")
            parameters.append(repository_url)
        if branch:
            filters.append("d.branch = %s")
            parameters.append(branch)
        parameters.append(top_k)
        where_clause = " and ".join(filters)
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select c.id as chunk_id, c.document_id,
                           d.repository_full_name, d.branch, d.commit_sha,
                           c.chunk_index, c.heading_path, c.section_title,
                           c.start_line, c.end_line, c.content,
                           greatest(-1.0, least(1.0, 1 - (c.embedding <=> %s::vector)))::float8 as score
                    from github_repository_summary_chunks c
                    join github_repository_summary_documents d on d.id = c.document_id
                    where {where_clause}
                    order by c.embedding <=> %s::vector
                    limit %s
                    """,
                    tuple(parameters[:-1] + [parameters[0], parameters[-1]]),
                )
                return [serialize_row(row) for row in cursor.fetchall()]
        except PsycopgError as exc:
            raise SummaryDatabaseError("Unable to search repository summary chunks") from exc

    def health(self) -> tuple[bool, bool]:
        try:
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute("select 1 as connected")
                connected = cursor.fetchone()["connected"] == 1
                cursor.execute(
                    "select exists(select 1 from pg_extension where extname = 'vector') as available"
                )
                available = bool(cursor.fetchone()["available"])
                return connected, available
        except PsycopgError:
            return False, False
