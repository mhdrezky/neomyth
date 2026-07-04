"""Neo-Parse service — orchestrates document upload, the job queue, and results.

Jobs are processed by a single background worker draining a FIFO queue —
one job at a time (GPU constraint). POST /parse/jobs returns immediately
with status QUEUED; clients read progress via the status/history endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import suppress
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from modules.parse import pdf, repository as repo
from modules.parse.processor import process_job
from modules.shared.db import get_session
from modules.shared.db.models import DocumentType, ParseJobStatus

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/parse")

# FIFO job queue drained by a single worker task (one job at a time).
# The inline schema travels in-memory with the queued item.
_queue: asyncio.Queue[tuple[uuid.UUID, dict | None]] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


async def _worker_loop() -> None:
    while True:
        job_id, schema = await _queue.get()
        try:
            # process_job handles its own errors, status updates, and webhooks.
            await process_job(job_id, schema)
        except Exception:
            logger.exception("Parse worker: job %s crashed", job_id)
        finally:
            _queue.task_done()


async def _recover_stale_jobs() -> None:
    """Fail jobs left QUEUED/PROCESSING by a previous run: their inline schema
    lived only in process memory, so requeueing them would silently run
    without it."""
    async with get_session() as session:
        stale = await repo.list_jobs_by_status(
            session, [ParseJobStatus.QUEUED, ParseJobStatus.PROCESSING]
        )
        for job in stale:
            await repo.update_job_status(
                session,
                job,
                ParseJobStatus.FAILED,
                error_msg="Interrupted by server restart; please resubmit.",
            )
    if stale:
        logger.warning("Parse worker: failed %d stale job(s) on startup", len(stale))


async def start_worker() -> None:
    """Start the queue worker (called from the API lifespan)."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    await _recover_stale_jobs()
    _worker_task = asyncio.create_task(_worker_loop())


async def stop_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await _worker_task
        _worker_task = None


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
    metadata: dict | None = None,
    webhook_url: str | None = None,
) -> dict:
    doc = await repo.get_document(session, document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    job = await repo.create_parse_job(
        session,
        document_id=document_id,
        schema_id=schema_id,
        metadata=metadata,
        webhook_url=webhook_url,
    )
    return {
        "job_id": str(job.id),
        "document_id": str(document_id),
        "status": job.status.value,
        "metadata": job.job_metadata,
    }


def schedule_processing(job_id: uuid.UUID, schema: dict | None) -> None:
    """Enqueue the job for the background worker (call after the job is committed)."""
    _queue.put_nowait((job_id, schema))


def render_page(storage_path: str, page_number: int) -> bytes:
    return pdf.render_page_png(storage_path, page_number)


async def _queue_positions(session: AsyncSession) -> dict[uuid.UUID, int]:
    """1-based FIFO position for every QUEUED job, from one ordered query."""
    queued = await repo.list_jobs_by_status(session, [ParseJobStatus.QUEUED])
    return {job.id: index + 1 for index, job in enumerate(queued)}


async def get_job_status(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict | None:
    """Lightweight job status for polling — no markdown/sections payload."""
    job = await repo.get_parse_job(session, job_id)
    if not job:
        return None
    queue_position = None
    if job.status == ParseJobStatus.QUEUED:
        queue_position = (await _queue_positions(session)).get(job.id)
    return {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "status": job.status.value,
        "queue_position": queue_position,
        "error_msg": job.error_msg,
        "metadata": job.job_metadata,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


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
        "metadata": job.job_metadata,
        "webhook_url": job.webhook_url,
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
) -> dict:
    """One paginated page of jobs (active + finished), newest-first."""
    rows = await repo.list_history_rows(session, limit=limit, offset=offset)
    total = await repo.count_parse_jobs(session)
    positions = await _queue_positions(session)
    items = [
        {
            "job_id": str(job.id),
            "document_id": str(job.document_id),
            "filename": doc.filename if doc else "unknown",
            "doc_type": doc.doc_type.value if doc else "OTHER",
            "status": job.status.value,
            "queue_position": positions.get(job.id),
            "error_msg": job.error_msg,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "section_count": section_count,
        }
        for job, doc, section_count in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
