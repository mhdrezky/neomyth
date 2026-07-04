"""CRUD operations for Neo-Parse entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.shared.db.models import (
    Document,
    DocumentType,
    ParseJob,
    ParseJobStatus,
    ParseSection,
    Schema,
)


# ── Documents ──────────────────────────────────────────────────────

async def create_document(
    session: AsyncSession,
    *,
    filename: str,
    storage_path: str,
    mime_type: str,
    size_bytes: int,
    page_count: int | None = None,
    doc_type: DocumentType = DocumentType.OTHER,
) -> Document:
    doc = Document(
        filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        size_bytes=size_bytes,
        page_count=page_count,
        doc_type=doc_type,
    )
    session.add(doc)
    await session.flush()
    return doc


async def get_document(session: AsyncSession, doc_id: uuid.UUID) -> Document | None:
    return await session.get(Document, doc_id)


async def list_documents(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    stmt = (
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_document(session: AsyncSession, doc_id: uuid.UUID) -> bool:
    doc = await session.get(Document, doc_id)
    if not doc:
        return False
    await session.delete(doc)
    await session.flush()
    return True


# ── Schemas ────────────────────────────────────────────────────────

async def create_schema(
    session: AsyncSession,
    *,
    name: str,
    content: dict,
    description: str | None = None,
    is_default: bool = False,
) -> Schema:
    schema = Schema(
        name=name,
        content=content,
        description=description,
        is_default=is_default,
    )
    session.add(schema)
    await session.flush()
    return schema


async def get_schema(session: AsyncSession, schema_id: uuid.UUID) -> Schema | None:
    return await session.get(Schema, schema_id)


async def list_schemas(session: AsyncSession) -> list[Schema]:
    stmt = select(Schema).order_by(Schema.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Parse Jobs ─────────────────────────────────────────────────────

async def create_parse_job(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    schema_id: uuid.UUID | None = None,
    metadata: dict | None = None,
    webhook_url: str | None = None,
) -> ParseJob:
    job = ParseJob(
        document_id=document_id,
        schema_id=schema_id,
        status=ParseJobStatus.QUEUED,
        job_metadata=metadata,
        webhook_url=webhook_url,
    )
    session.add(job)
    await session.flush()
    return job


async def get_parse_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    with_sections: bool = False,
) -> ParseJob | None:
    if with_sections:
        stmt = (
            select(ParseJob)
            .options(selectinload(ParseJob.sections))
            .where(ParseJob.id == job_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    return await session.get(ParseJob, job_id)


async def list_parse_jobs(
    session: AsyncSession,
    *,
    document_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ParseJob]:
    stmt = select(ParseJob).order_by(ParseJob.created_at.desc())
    if document_id:
        stmt = stmt.where(ParseJob.document_id == document_id)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_parse_jobs(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(ParseJob))
    return int(result.scalar_one())


async def list_history_rows(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[ParseJob, Document | None, int]]:
    """History page rows: (job, document, section_count) newest-first,
    in one query instead of per-job lookups."""
    section_counts = (
        select(
            ParseSection.job_id,
            func.count(ParseSection.id).label("section_count"),
        )
        .group_by(ParseSection.job_id)
        .subquery()
    )
    stmt = (
        select(
            ParseJob,
            Document,
            func.coalesce(section_counts.c.section_count, 0),
        )
        .join(Document, ParseJob.document_id == Document.id, isouter=True)
        .outerjoin(section_counts, section_counts.c.job_id == ParseJob.id)
        .order_by(ParseJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1], int(row[2])) for row in result.all()]


async def list_jobs_by_status(
    session: AsyncSession,
    statuses: list[ParseJobStatus],
) -> list[ParseJob]:
    """Jobs in the given statuses, FIFO order (creation time, then id)."""
    stmt = (
        select(ParseJob)
        .where(ParseJob.status.in_(statuses))
        .order_by(ParseJob.created_at, ParseJob.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_job_status(
    session: AsyncSession,
    job: ParseJob,
    status: ParseJobStatus,
    *,
    error_msg: str | None = None,
    markdown_output: str | None = None,
    json_output: dict | None = None,
) -> ParseJob:
    now = datetime.now(timezone.utc)
    job.status = status
    if status == ParseJobStatus.PROCESSING:
        job.started_at = now
    elif status in (ParseJobStatus.COMPLETED, ParseJobStatus.FAILED):
        job.completed_at = now
    if error_msg is not None:
        job.error_msg = error_msg
    if markdown_output is not None:
        job.markdown_output = markdown_output
    if json_output is not None:
        job.json_output = json_output
    await session.flush()
    return job


# ── Parse Sections ─────────────────────────────────────────────────

async def create_sections_bulk(
    session: AsyncSession,
    job_id: uuid.UUID,
    sections: list[dict],
) -> list[ParseSection]:
    objs = [
        ParseSection(
            job_id=job_id,
            page_number=s.get("page_number", 1),
            label=s["label"],
            region=s["region"],
            rect_top=s["rect_top"],
            rect_left=s["rect_left"],
            rect_width=s["rect_width"],
            rect_height=s["rect_height"],
            markdown=s["markdown"],
            json_data=s.get("json_data"),
            confidence=s.get("confidence"),
            sort_order=s.get("sort_order", i),
        )
        for i, s in enumerate(sections)
    ]
    session.add_all(objs)
    await session.flush()
    return objs


async def get_sections_by_job(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> list[ParseSection]:
    stmt = (
        select(ParseSection)
        .where(ParseSection.job_id == job_id)
        .order_by(ParseSection.sort_order)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
