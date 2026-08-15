from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

from app.database import get_connection
from app.impact_analysis.domain import DesignEvidenceItem, DesignEvidencePackage


DESIGN_NAME_MARKERS = (
    "architecture",
    "technical-design",
    "technical_design",
    "api-design",
    "api_design",
    "component-design",
    "component_design",
)


class DesignDocumentRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory

    def search(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 12,
    ) -> DesignEvidencePackage:
        normalized_query = " ".join(query.split())[:4000]
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select d.doc_id document_id, d.doc_nm document_name,
                       d.doc_type document_type, d.file_checksum checksum,
                       d.ingestion_metadata,
                       c.chunk_id, c.chunk_index, c.chunk_text text,
                       coalesce(c.section_path, array[]::text[]) section_path,
                       coalesce(c.page_numbers, array[]::integer[]) page_numbers,
                       case when %s = '' then 0.0 else
                         ts_rank_cd(
                           to_tsvector('english', c.chunk_text),
                           plainto_tsquery('english', %s)
                         )
                       end relevance_score
                from documents d
                join document_chunks c on c.doc_id=d.doc_id
                where d.project_id=%s and d.doc_status='EMBEDDED'
                  and (
                    lower(coalesce(d.ingestion_metadata->>'approved_for_impact_analysis',''))
                      in ('true','1','yes')
                    or lower(d.doc_nm) like '%%architecture%%'
                    or lower(coalesce(d.ingestion_metadata->>'document_role','')) in
                       ('architecture','technical_design','api_design','component_design','standard')
                  )
                order by relevance_score desc, d.last_update_timestamp desc,
                         c.chunk_index
                limit %s
                """,
                (normalized_query, normalized_query, project_id, limit),
            )
            rows = cursor.fetchall()
        items = []
        for row in rows:
            metadata = row.pop("ingestion_metadata") or {}
            basis = (
                "APPROVED_METADATA"
                if metadata.get("approved_for_impact_analysis")
                else "ARCHITECTURE_NAME_OR_ROLE"
            )
            items.append(DesignEvidenceItem(**row, approval_basis=basis))
        return DesignEvidencePackage(
            project_id=project_id, query=normalized_query, items=items
        )
