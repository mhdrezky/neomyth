"""Parse module HTTP routes — thin transport layer."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import BaseModel

from modules.parse import pdf, repository as repo, service
from modules.shared.db import get_session
from modules.shared.utils import json_schema as schema_utils

router = APIRouter(prefix="/parse", tags=["parse"])


class StartJobRequest(BaseModel):
    document_id: uuid.UUID
    schema_id: uuid.UUID | None = None
    schema_text: str | None = None  # inline JSON schema from the editor


class StartJobResponse(BaseModel):
    job_id: str
    document_id: str
    status: str


class UploadResponse(BaseModel):
    id: str
    filename: str
    size_bytes: int
    doc_type: str


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile) -> UploadResponse:
    if not file.filename:
        raise HTTPException(400, "Filename is required")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF files are supported")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 25 MB)")
    if not pdf.is_pdf(content):
        raise HTTPException(415, "File is not a valid PDF")

    async with get_session() as session:
        result = await service.upload_document(
            session,
            filename=file.filename,
            content=content,
            mime_type=file.content_type or "application/pdf",
        )
    return UploadResponse(**result)


@router.post("/jobs", response_model=StartJobResponse)
async def start_job(body: StartJobRequest) -> StartJobResponse:
    schema: dict | None = None
    if body.schema_text and body.schema_text.strip():
        try:
            schema = json.loads(body.schema_text)
        except json.JSONDecodeError:
            raise HTTPException(400, "schema_text is not valid JSON")
        if not isinstance(schema, dict):
            raise HTTPException(400, "schema_text must be a JSON object")
        # Real JSON Schemas must be valid draft-07; plain example objects
        # ("shape hints") are passed through to the LLM unvalidated.
        if schema_utils.is_json_schema(schema):
            try:
                schema_utils.check_schema(schema)
            except ValueError as e:
                raise HTTPException(400, str(e))

    async with get_session() as session:
        try:
            result = await service.start_parse_job(
                session,
                document_id=body.document_id,
                schema_id=body.schema_id,
            )
        except ValueError as e:
            raise HTTPException(404, str(e))

    # Job row is committed now — safe to kick off background processing.
    service.schedule_processing(uuid.UUID(result["job_id"]), schema)
    return StartJobResponse(**result)


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID) -> dict:
    async with get_session() as session:
        result = await service.get_job_result(session, job_id)
    if not result:
        raise HTTPException(404, f"Job {job_id} not found")
    return result


@router.get("/history")
async def list_history(limit: int = 20, offset: int = 0) -> list[dict]:
    async with get_session() as session:
        return await service.list_history(session, limit=limit, offset=offset)


@router.get("/documents")
async def list_documents(limit: int = 50, offset: int = 0) -> list[dict]:
    async with get_session() as session:
        docs = await repo.list_documents(session, limit=limit, offset=offset)
        return [
            {
                "id": str(d.id),
                "filename": d.filename,
                "size_bytes": d.size_bytes,
                "doc_type": d.doc_type.value,
                "page_count": d.page_count,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]


@router.get("/documents/{doc_id}/pages/{page_number}")
async def get_page_image(doc_id: uuid.UUID, page_number: int) -> Response:
    async with get_session() as session:
        doc = await repo.get_document(session, doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")
    try:
        png = service.render_page(doc.storage_path, page_number)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(404, str(e))
    return Response(content=png, media_type="image/png")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: uuid.UUID) -> dict:
    async with get_session() as session:
        deleted = await repo.delete_document(session, doc_id)
    if not deleted:
        raise HTTPException(404, f"Document {doc_id} not found")
    return {"deleted": True}


@router.get("/schemas")
async def list_schemas() -> list[dict]:
    async with get_session() as session:
        schemas = await repo.list_schemas(session)
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "is_default": s.is_default,
                "created_at": s.created_at.isoformat(),
            }
            for s in schemas
        ]
