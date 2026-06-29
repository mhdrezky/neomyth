"""Neo-Parse service — orchestrates document upload, parsing, and results.

This is the prototype layer (no LLM integration yet). It stores documents,
creates parse jobs, and returns demo results. The actual LLM-based extraction
will be wired in later.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from modules.parse import pdf, repository as repo
from modules.parse.processor import process_job
from modules.shared.db.models import DocumentType

UPLOAD_DIR = Path("uploads/parse")

# Keep strong references to background parse tasks so they aren't GC'd.
_background_tasks: set[asyncio.Task] = set()


def _detect_doc_type(filename: str) -> DocumentType:
    name = filename.lower()
    if "invoice" in name:
        return DocumentType.INVOICE
    if "contract" in name or "msa" in name:
        return DocumentType.CONTRACT
    if "receipt" in name:
        return DocumentType.RECEIPT
    if "report" in name or "earning" in name:
        return DocumentType.REPORT
    return DocumentType.OTHER


async def upload_document(
    session: AsyncSession,
    *,
    filename: str,
    content: bytes,
    mime_type: str = "application/pdf",
) -> dict:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4()
    storage_path = UPLOAD_DIR / f"{doc_id}_{filename}"
    storage_path.write_bytes(content)

    doc = await repo.create_document(
        session,
        filename=filename,
        storage_path=str(storage_path),
        mime_type=mime_type,
        size_bytes=len(content),
        doc_type=_detect_doc_type(filename),
    )
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "size_bytes": doc.size_bytes,
        "doc_type": doc.doc_type.value,
    }


async def start_parse_job(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    schema_id: uuid.UUID | None = None,
) -> dict:
    doc = await repo.get_document(session, document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    job = await repo.create_parse_job(
        session,
        document_id=document_id,
        schema_id=schema_id,
    )
    return {
        "job_id": str(job.id),
        "document_id": str(document_id),
        "status": job.status.value,
    }


def schedule_processing(job_id: uuid.UUID, schema: dict | None) -> None:
    """Spawn the parse pipeline in the background (call after the job is committed)."""
    task = asyncio.create_task(process_job(job_id, schema))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def render_page(storage_path: str, page_number: int) -> bytes:
    return pdf.render_page_png(storage_path, page_number)


async def get_job_result(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict | None:
    job = await repo.get_parse_job(session, job_id, with_sections=True)
    if not job:
        return None

    return {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "status": job.status.value,
        "error_msg": job.error_msg,
        "markdown_output": job.markdown_output,
        "json_output": job.json_output,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "sections": [
            {
                "id": str(s.id),
                "page_number": s.page_number,
                "label": s.label,
                "region": s.region,
                "rect": {
                    "top": s.rect_top,
                    "left": s.rect_left,
                    "width": s.rect_width,
                    "height": s.rect_height,
                },
                "markdown": s.markdown,
                "json_data": s.json_data,
                "confidence": s.confidence,
                "sort_order": s.sort_order,
            }
            for s in sorted(job.sections, key=lambda s: s.sort_order)
        ],
    }


async def list_history(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    jobs = await repo.list_parse_jobs(session, limit=limit, offset=offset)
    results = []
    for job in jobs:
        doc = await repo.get_document(session, job.document_id)
        results.append({
            "job_id": str(job.id),
            "filename": doc.filename if doc else "unknown",
            "doc_type": doc.doc_type.value if doc else "OTHER",
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "section_count": len(
                await repo.get_sections_by_job(session, job.id)
            ),
        })
    return results
