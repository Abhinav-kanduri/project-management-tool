from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from openai import OpenAI
from psycopg.types.json import Jsonb

from app.config import (
    KNOWLEDGE_EMBEDDING_BATCH_SIZE,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)
from app.database import get_connection
from app.document_reader import _extract_text

logger = logging.getLogger(__name__)
embedding_client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=60.0,
    max_retries=2,
)


def _event(
    document: dict[str, Any],
    stage: str,
    status: str,
    message: str,
    *,
    attempt: int,
    details: dict[str, Any] | None = None,
) -> None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into document_ingestion_events (
                document_id,
                product_space_id,
                project_id,
                stage,
                status,
                attempt,
                message,
                details,
                completed_at
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s,
                case when %s <> 'RUNNING' then now() else null end
            )
            """,
            (
                document["doc_id"],
                document["product_space_id"],
                document["project_id"],
                stage,
                status,
                attempt,
                message,
                Jsonb(details or {}),
                status,
            ),
        )
        connection.commit()


def _set_status(
    document_id: str,
    status: str,
    *,
    raw_text: str | None = None,
    parser_name: str | None = None,
) -> None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            update documents
            set doc_status = %s,
                doc_raw_text = coalesce(%s, doc_raw_text),
                parser_name = coalesce(%s::text, parser_name),
                parser_version = case
                    when %s::text is not null then '1'
                    else parser_version
                end,
                last_update_timestamp = now()
            where doc_id = %s
            """,
            (status, raw_text, parser_name, parser_name, document_id),
        )
        connection.commit()


def _claim_job(document_id: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            update document_ingestion_jobs
            set status = 'RUNNING',
                locked_at = now(),
                locked_by = %s,
                updated_at = now()
            where id = (
                select id
                from document_ingestion_jobs
                where document_id = %s
                  and status = 'PENDING'
                  and available_at <= now()
                order by id
                for update skip locked
                limit 1
            )
            returning *
            """,
            ("fastapi-background-task", document_id),
        )
        job = cursor.fetchone()
        connection.commit()
        return job


def _load_document(document_id: str) -> dict[str, Any] | None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "select * from documents where doc_id = %s",
            (document_id,),
        )
        return cursor.fetchone()


def _chunks(text: str, maximum: int = 4000) -> list[dict[str, Any]]:
    paragraphs = [
        paragraph.strip()
        for paragraph in text.replace("\r\n", "\n").split("\n\n")
        if paragraph.strip()
    ]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > maximum:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), maximum):
                chunks.append(paragraph[start : start + maximum])
            continue
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > maximum:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return [
        {
            "chunk_index": index,
            "chunk_text": chunk,
            "token_count": len(chunk.split()),
            "metadata": {},
        }
        for index, chunk in enumerate(chunks)
    ]


def _embed(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    embedded: list[dict[str, Any]] = []
    for start in range(0, len(chunks), KNOWLEDGE_EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + KNOWLEDGE_EMBEDDING_BATCH_SIZE]
        response = embedding_client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=[item["chunk_text"] for item in batch],
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        )
        if len(response.data) != len(batch):
            raise RuntimeError(
                "Embedding response did not match the requested batch."
            )
        for item, result in zip(batch, response.data):
            if len(result.embedding) != OPENAI_EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    "Embedding vector has an unexpected dimension."
                )
            embedded.append({**item, "embedding": result.embedding})
    return embedded


def _replace_chunks(
    document: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "delete from document_chunks where doc_id = %s",
            (document["doc_id"],),
        )
        for chunk in chunks:
            vector = "[" + ",".join(
                format(value, ".9g") for value in chunk["embedding"]
            ) + "]"
            cursor.execute(
                """
                insert into document_chunks (
                    doc_id,
                    chunk_id,
                    chunk_text,
                    chunk_vector,
                    product_space_id,
                    project_id,
                    release_id,
                    environment_id,
                    chunk_index,
                    token_count,
                    page_numbers,
                    section_path,
                    chunk_metadata,
                    embedding_model,
                    embedding_dimensions,
                    embedding_status
                )
                values (
                    %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 'COMPLETED'
                )
                """,
                (
                    document["doc_id"],
                    f"{document['doc_id']}-{chunk['chunk_index']:06d}",
                    chunk["chunk_text"],
                    vector,
                    document["product_space_id"],
                    document["project_id"],
                    document["release_id"],
                    document["environment_id"],
                    chunk["chunk_index"],
                    chunk["token_count"],
                    [],
                    [],
                    Jsonb(chunk["metadata"]),
                    OPENAI_EMBEDDING_MODEL,
                    OPENAI_EMBEDDING_DIMENSIONS,
                ),
            )
        connection.commit()


def process_document(document_id: str) -> None:
    job = _claim_job(document_id)
    if not job:
        return
    attempt = job["attempt"]
    document = _load_document(document_id)
    if not document:
        return

    current_stage = "UPLOADED"
    try:
        source_path = Path(document["storage_uri"])
        if not source_path.is_file():
            raise FileNotFoundError("The stored document file is missing.")
        _set_status(document_id, "UPLOADED")
        _event(
            document,
            "UPLOADED",
            "COMPLETED",
            "Original document stored",
            attempt=attempt,
        )

        current_stage = "PARSING"
        _set_status(document_id, "PARSING")
        _event(
            document,
            "PARSING",
            "RUNNING",
            "Document parsing started",
            attempt=attempt,
        )
        raw_text = _extract_text(
            document["doc_nm"], source_path.read_bytes()
        ).strip()
        if not raw_text:
            raise ValueError("The parser produced no readable text.")
        _set_status(
            document_id,
            "PARSED",
            raw_text=raw_text,
            parser_name="pypdf/python-docx",
        )
        _event(
            document,
            "PARSING",
            "COMPLETED",
            "Document parsing completed",
            attempt=attempt,
            details={"character_count": len(raw_text)},
        )

        current_stage = "CHUNKING"
        _set_status(document_id, "CHUNKING")
        _event(
            document,
            "CHUNKING",
            "RUNNING",
            "Document chunking started",
            attempt=attempt,
        )
        prepared_chunks = _chunks(raw_text)
        if not prepared_chunks:
            raise ValueError("The parser produced no usable chunks.")
        _set_status(document_id, "CHUNKED")
        _event(
            document,
            "CHUNKING",
            "COMPLETED",
            f"Created {len(prepared_chunks)} chunks",
            attempt=attempt,
            details={"chunk_count": len(prepared_chunks)},
        )

        current_stage = "EMBEDDING"
        _set_status(document_id, "EMBEDDING")
        _event(
            document,
            "EMBEDDING",
            "RUNNING",
            "Embedding generation started",
            attempt=attempt,
        )
        embedded_chunks = _embed(prepared_chunks)
        _replace_chunks(document, embedded_chunks)
        _set_status(document_id, "EMBEDDED")
        _event(
            document,
            "EMBEDDING",
            "COMPLETED",
            f"Stored {len(embedded_chunks)} embeddings",
            attempt=attempt,
            details={
                "chunk_count": len(embedded_chunks),
                "embedding_model": OPENAI_EMBEDDING_MODEL,
                "embedding_dimensions": OPENAI_EMBEDDING_DIMENSIONS,
            },
        )
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update document_ingestion_jobs
                set status = 'COMPLETED',
                    updated_at = now()
                where id = %s
                """,
                (job["id"],),
            )
            connection.commit()
    except Exception as error:
        logger.exception("Knowledge ingestion failed for %s", document_id)
        safe_message = str(error)[:2000]
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                update documents
                set doc_status = 'FAILED',
                    ingestion_error_code = %s,
                    ingestion_error = %s,
                    last_update_timestamp = now()
                where doc_id = %s
                """,
                (f"{current_stage}_FAILED", safe_message, document_id),
            )
            cursor.execute(
                """
                update document_ingestion_jobs
                set status = 'FAILED',
                    last_error = %s,
                    updated_at = now()
                where id = %s
                """,
                (safe_message, job["id"]),
            )
            connection.commit()
        _event(
            document,
            current_stage,
            "FAILED",
            f"{current_stage.title()} failed",
            attempt=attempt,
            details={"error_code": f"{current_stage}_FAILED"},
        )
