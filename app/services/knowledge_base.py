from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from psycopg.types.json import Jsonb

from app.config import (
    KNOWLEDGE_UPLOAD_MAX_BYTES,
    KNOWLEDGE_UPLOAD_ROOT,
    WORKSPACE_ENVIRONMENTS,
)
from app.database import get_connection

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",
}


def knowledge_error(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    **details: Any,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details,
        },
    )


def validate_workspace_scope(
    cursor,
    product_space_id: UUID,
    project_id: UUID,
    release_id: UUID | None = None,
    environment_id: str | None = None,
) -> dict[str, Any]:
    cursor.execute(
        """
        select p.id, p.name, p.product_space_id
        from projects p
        where p.id = %s
          and p.product_space_id = %s
          and p.archived_at is null
        """,
        (project_id, product_space_id),
    )
    project = cursor.fetchone()
    if not project:
        knowledge_error(
            404,
            "PROJECT_NOT_FOUND",
            "The selected Project was not found in this Product Space.",
        )

    if release_id:
        cursor.execute(
            """
            select 1
            from releases
            where id = %s
              and project_id = %s
              and archived_at is null
            """,
            (release_id, project_id),
        )
        if not cursor.fetchone():
            knowledge_error(
                422,
                "RELEASE_OUTSIDE_PROJECT",
                "The selected Release does not belong to this Project.",
            )

    if environment_id and environment_id not in WORKSPACE_ENVIRONMENTS:
        knowledge_error(
            422,
            "ENVIRONMENT_UNAVAILABLE",
            "The selected Environment is not available.",
        )
    return project


def validate_file(file: UploadFile) -> tuple[str, str]:
    if not file.filename:
        knowledge_error(400, "INVALID_UPLOAD", "Filename is required.")
    safe_filename = Path(file.filename).name
    if safe_filename in {"", ".", ".."}:
        knowledge_error(400, "INVALID_UPLOAD", "Filename is invalid.")
    extension = Path(safe_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        knowledge_error(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "Supported document types are PDF, DOCX, Markdown, and plain text.",
        )
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        knowledge_error(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported content type: {content_type}.",
        )
    return safe_filename, content_type


async def persist_upload(
    file: UploadFile,
    product_space_id: UUID,
    project_id: UUID,
) -> tuple[str, Path, int, str, str]:
    safe_filename, content_type = validate_file(file)
    document_id = str(uuid4())
    directory = (
        Path(KNOWLEDGE_UPLOAD_ROOT)
        / str(product_space_id)
        / str(project_id)
        / document_id
    )
    directory.mkdir(parents=True, exist_ok=False)
    stored_path = directory / safe_filename
    checksum = hashlib.sha256()
    total_size = 0

    try:
        with stored_path.open("wb") as destination:
            while content := await file.read(1024 * 1024):
                total_size += len(content)
                if total_size > KNOWLEDGE_UPLOAD_MAX_BYTES:
                    knowledge_error(
                        413,
                        "FILE_TOO_LARGE",
                        "The file exceeds the configured upload limit.",
                    )
                checksum.update(content)
                destination.write(content)
    except Exception:
        stored_path.unlink(missing_ok=True)
        if directory.exists():
            directory.rmdir()
        raise
    finally:
        await file.close()

    if total_size == 0:
        stored_path.unlink(missing_ok=True)
        directory.rmdir()
        knowledge_error(400, "INVALID_UPLOAD", "The uploaded file is empty.")

    return (
        document_id,
        stored_path,
        total_size,
        checksum.hexdigest(),
        content_type,
    )


def remove_stored_file(storage_uri: str | None) -> None:
    if not storage_uri:
        return
    path = Path(storage_uri)
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def serialize_document(row: dict[str, Any]) -> dict[str, Any]:
    def value(item: Any) -> Any:
        if isinstance(item, UUID):
            return str(item)
        if hasattr(item, "isoformat"):
            return item.isoformat()
        return item

    return {key: value(item) for key, item in row.items()}


def create_document(
    *,
    document_id: str,
    filename: str,
    document_type: str,
    product_space_id: UUID,
    project_id: UUID,
    release_id: UUID | None,
    environment_id: str | None,
    storage_uri: str,
    mime_type: str,
    file_size_bytes: int,
    file_checksum: str,
    description: str | None,
    actor: str,
) -> None:
    with get_connection() as connection, connection.cursor() as cursor:
        validate_workspace_scope(
            cursor,
            product_space_id,
            project_id,
            release_id,
            environment_id,
        )
        cursor.execute(
            """
            select doc_id
            from documents
            where product_space_id = %s
              and project_id = %s
              and file_checksum = %s
              and doc_status <> 'FAILED'
            limit 1
            """,
            (product_space_id, project_id, file_checksum),
        )
        duplicate = cursor.fetchone()
        if duplicate:
            knowledge_error(
                409,
                "DUPLICATE_DOCUMENT",
                "This document already exists in the selected Project.",
                existing_document_id=duplicate["doc_id"],
            )
        cursor.execute(
            """
            insert into documents (
                doc_id,
                doc_nm,
                doc_type,
                doc_raw_text,
                doc_status,
                product_space_id,
                project_id,
                release_id,
                environment_id,
                storage_uri,
                mime_type,
                file_size_bytes,
                file_checksum,
                ingestion_metadata,
                created_by
            )
            values (
                %s, %s, %s, '', 'RECEIVED', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                document_id,
                filename,
                document_type,
                product_space_id,
                project_id,
                release_id,
                environment_id,
                storage_uri,
                mime_type,
                file_size_bytes,
                file_checksum,
                Jsonb(
                    {
                        "description": description,
                        "original_filename": filename,
                    }
                ),
                actor,
            ),
        )
        cursor.execute(
            """
            insert into document_ingestion_events (
                document_id,
                product_space_id,
                project_id,
                stage,
                status,
                message,
                completed_at
            )
            values (%s, %s, %s, 'RECEIVED', 'COMPLETED', %s, now())
            """,
            (
                document_id,
                product_space_id,
                project_id,
                "Document accepted for ingestion",
            ),
        )
        cursor.execute(
            """
            insert into document_ingestion_jobs (
                document_id,
                requested_stage,
                status
            )
            values (%s, 'PARSING', 'PENDING')
            """,
            (document_id,),
        )
        connection.commit()


def get_scoped_document(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> dict[str, Any]:
    with get_connection() as connection, connection.cursor() as cursor:
        validate_workspace_scope(cursor, product_space_id, project_id)
        cursor.execute(
            """
            select d.*,
                   count(c.id)::integer as chunk_count,
                   count(c.id) filter (
                       where c.embedding_status = 'COMPLETED'
                   )::integer as embedded_chunk_count
            from documents d
            left join document_chunks c on c.doc_id = d.doc_id
            where d.doc_id = %s
              and d.product_space_id = %s
              and d.project_id = %s
            group by d.doc_id
            """,
            (document_id, product_space_id, project_id),
        )
        row = cursor.fetchone()
        if not row:
            knowledge_error(
                404,
                "DOCUMENT_NOT_FOUND",
                "The document was not found in the selected Project.",
            )
        return serialize_document(row)


def list_scoped_documents(
    product_space_id: UUID,
    project_id: UUID,
) -> list[dict[str, Any]]:
    with get_connection() as connection, connection.cursor() as cursor:
        validate_workspace_scope(cursor, product_space_id, project_id)
        cursor.execute(
            """
            select d.*,
                   count(c.id)::integer as chunk_count,
                   count(c.id) filter (
                       where c.embedding_status = 'COMPLETED'
                   )::integer as embedded_chunk_count
            from documents d
            left join document_chunks c on c.doc_id = d.doc_id
            where d.product_space_id = %s
              and d.project_id = %s
            group by d.doc_id
            order by d.last_update_timestamp desc
            """,
            (product_space_id, project_id),
        )
        return [serialize_document(row) for row in cursor.fetchall()]


def document_status(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> dict[str, Any]:
    document = get_scoped_document(
        product_space_id, project_id, document_id
    )
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select stage, status, attempt, message, details,
                   started_at, completed_at, created_at
            from document_ingestion_events
            where document_id = %s
              and product_space_id = %s
              and project_id = %s
            order by created_at
            """,
            (document_id, product_space_id, project_id),
        )
        events = [serialize_document(row) for row in cursor.fetchall()]
    return {"document": document, "events": events}


def knowledge_stats(
    product_space_id: UUID,
    project_id: UUID,
) -> dict[str, int]:
    with get_connection() as connection, connection.cursor() as cursor:
        validate_workspace_scope(cursor, product_space_id, project_id)
        cursor.execute(
            """
            select
                count(distinct d.doc_id)::integer as documents,
                count(c.id)::integer as chunks,
                count(c.id) filter (
                    where c.embedding_status = 'COMPLETED'
                )::integer as embedded_chunks,
                count(distinct d.doc_id) filter (
                    where d.doc_status = 'EMBEDDED'
                )::integer as embedded_documents,
                count(distinct d.doc_id) filter (
                    where d.doc_status in (
                        'RECEIVED', 'UPLOADED', 'PARSING', 'PARSED',
                        'CHUNKING', 'CHUNKED', 'EMBEDDING'
                    )
                )::integer as processing,
                count(distinct d.doc_id) filter (
                    where d.doc_status = 'FAILED'
                )::integer as failed
            from documents d
            left join document_chunks c on c.doc_id = d.doc_id
            where d.product_space_id = %s
              and d.project_id = %s
            """,
            (product_space_id, project_id),
        )
        return cursor.fetchone()


def retry_document(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> None:
    with get_connection() as connection, connection.cursor() as cursor:
        validate_workspace_scope(cursor, product_space_id, project_id)
        cursor.execute(
            """
            select doc_status
            from documents
            where doc_id = %s
              and product_space_id = %s
              and project_id = %s
            for update
            """,
            (document_id, product_space_id, project_id),
        )
        document = cursor.fetchone()
        if not document:
            knowledge_error(
                404,
                "DOCUMENT_NOT_FOUND",
                "The document was not found in the selected Project.",
            )
        if document["doc_status"] != "FAILED":
            knowledge_error(
                409,
                "DOCUMENT_NOT_RETRYABLE",
                "Only failed documents can be retried.",
            )
        cursor.execute(
            """
            update documents
            set doc_status = 'RECEIVED',
                ingestion_error_code = null,
                ingestion_error = null,
                last_update_timestamp = now()
            where doc_id = %s
            """,
            (document_id,),
        )
        cursor.execute(
            """
            insert into document_ingestion_jobs (
                document_id,
                requested_stage,
                status,
                attempt
            )
            select %s, 'PARSING', 'PENDING',
                   coalesce(max(attempt), 0) + 1
            from document_ingestion_jobs
            where document_id = %s
            """,
            (document_id, document_id),
        )
        connection.commit()


def delete_document(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> str | None:
    with get_connection() as connection, connection.cursor() as cursor:
        validate_workspace_scope(cursor, product_space_id, project_id)
        cursor.execute(
            """
            delete from documents
            where doc_id = %s
              and product_space_id = %s
              and project_id = %s
            returning storage_uri
            """,
            (document_id, product_space_id, project_id),
        )
        deleted = cursor.fetchone()
        if not deleted:
            knowledge_error(
                404,
                "DOCUMENT_NOT_FOUND",
                "The document was not found in the selected Project.",
            )
        connection.commit()
        return deleted["storage_uri"]


def normalized_document_type(
    explicit_type: str | None,
    filename: str,
    mime_type: str,
) -> str:
    if explicit_type:
        return re.sub(r"[^a-zA-Z0-9_.-]", "-", explicit_type)[:80]
    return Path(filename).suffix.lower().lstrip(".") or mime_type
