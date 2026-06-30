"""Documents router (Core).

Exposes document ingestion at the Gateway. Uploading a document triggers the
Core ingestion pipeline which records a `resource_created` event in the Event
Store. This router contains NO chat/LLM logic — that belongs to the Desktop
(Application) layer, which would consume this endpoint via the SDK.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from gabriel.api.dependencies import (
    get_document_ingestion_service,
    get_execution_context,
    get_gateway_service,
    GatewayService,
)
from gabriel.api.schema import DocumentResponse
from gabriel.document.normalizer import NormalizationError
from gabriel.document.service import DocumentIngestionService
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    source_uri: str | None = Form(default=None),
    context: ExecutionContext = Depends(get_execution_context),
    service: DocumentIngestionService = Depends(get_document_ingestion_service),
) -> DocumentResponse:
    """Upload and ingest a document as a Resource.

    Emits a `resource_created` event (ResourceCreated) in the Event Store.
    """
    content = await file.read()
    try:
        result = await service.ingest(
            context=context,
            filename=file.filename or "upload",
            content=content,
            source_uri=source_uri,
            media_type=file.content_type,
        )
    except NormalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    document = result.document
    return DocumentResponse(
        grn=str(document.grn),
        state=document.state.value,
        filename=file.filename or "upload",
        media_type=document.media_type,
        source_uri=document.source_uri,
        content_hash=document.content_hash,
        byte_size=document.byte_size,
        event_id=result.event.id,
        event_type=result.event.type,
    )


@router.get("/{grn:path}", response_model=dict)
async def get_document(
    grn: str,
    service: GatewayService = Depends(get_gateway_service),
) -> dict:
    """Fetch the reconstructed document resource state from the Event Store."""
    resource = service.get_resource(grn)
    if not resource:
        raise HTTPException(status_code=404, detail="Document not found")
    return resource
