from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Header,
    UploadFile,
    status,
)

from app.services.knowledge_base import (
    create_document,
    delete_document,
    document_status,
    get_scoped_document,
    knowledge_stats,
    list_scoped_documents,
    normalized_document_type,
    persist_upload,
    remove_stored_file,
    retry_document,
)
from app.services.knowledge_ingestion import process_document

router = APIRouter(prefix="/api/v1", tags=["Knowledge Base"])


@router.post(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/documents",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_knowledge_document(
    product_space_id: UUID,
    project_id: UUID,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    release_id: Annotated[UUID | None, Form()] = None,
    environment_id: Annotated[str | None, Form()] = None,
    document_type: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    x_actor: Annotated[str, Header()] = "local-user",
) -> dict:
    (
        document_id,
        stored_path,
        total_size,
        checksum,
        content_type,
    ) = await persist_upload(file, product_space_id, project_id)
    try:
        create_document(
            document_id=document_id,
            filename=stored_path.name,
            document_type=normalized_document_type(
                document_type, stored_path.name, content_type
            ),
            product_space_id=product_space_id,
            project_id=project_id,
            release_id=release_id,
            environment_id=environment_id,
            storage_uri=str(stored_path.resolve()),
            mime_type=content_type,
            file_size_bytes=total_size,
            file_checksum=checksum,
            description=description,
            actor=x_actor,
        )
    except Exception:
        remove_stored_file(str(stored_path))
        raise
    background_tasks.add_task(process_document, document_id)
    return {
        "document_id": document_id,
        "filename": stored_path.name,
        "product_space_id": str(product_space_id),
        "project_id": str(project_id),
        "release_id": str(release_id) if release_id else None,
        "environment_id": environment_id,
        "status": "RECEIVED",
        "message": "Document accepted for ingestion",
    }


@router.get(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/documents"
)
def list_knowledge_documents(
    product_space_id: UUID,
    project_id: UUID,
) -> dict:
    return {
        "items": list_scoped_documents(product_space_id, project_id),
        "product_space_id": str(product_space_id),
        "project_id": str(project_id),
    }


@router.get(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/stats"
)
def get_knowledge_stats(
    product_space_id: UUID,
    project_id: UUID,
) -> dict:
    return knowledge_stats(product_space_id, project_id)


@router.get(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/documents/{document_id}"
)
def get_knowledge_document(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> dict:
    return get_scoped_document(product_space_id, project_id, document_id)


@router.get(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/documents/{document_id}/status"
)
def get_knowledge_document_status(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> dict:
    return document_status(product_space_id, project_id, document_id)


@router.post(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/documents/{document_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_knowledge_document(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    retry_document(product_space_id, project_id, document_id)
    background_tasks.add_task(process_document, document_id)
    return {
        "document_id": document_id,
        "status": "RECEIVED",
        "message": "Document retry accepted",
    }


@router.delete(
    "/product-spaces/{product_space_id}/projects/{project_id}"
    "/knowledge-base/documents/{document_id}"
)
def delete_knowledge_document(
    product_space_id: UUID,
    project_id: UUID,
    document_id: str,
) -> dict:
    storage_uri = delete_document(
        product_space_id, project_id, document_id
    )
    remove_stored_file(storage_uri)
    return {"deleted": True, "document_id": document_id}
