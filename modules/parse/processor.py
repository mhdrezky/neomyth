"""Parse pipeline: extract PDF layout, run the LLM, store grounded sections.

Runs in the background after a job is created. Opens its own DB session so it
is independent of the request lifecycle.
"""

from __future__ import annotations

import uuid
from typing import Any

from api.config import get_settings
from modules.parse import pdf, repository as repo
from modules.parse.clients.llm import ParseLLMClient
from modules.shared.db import get_session
from modules.shared.db.models import ParseJobStatus


def _group_by_label(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a document object from labelled section text (real content)."""
    grouped: dict[str, list[str]] = {}
    for s in sections:
        grouped.setdefault(s["label"], []).append(s["markdown"])
    return {
        label: (texts[0] if len(texts) == 1 else texts)
        for label, texts in grouped.items()
    }


def _region_code(top_pct: float, seq: int) -> str:
    """A readable grounding badge like 'A1', 'B2' from vertical band + order."""
    band = chr(ord("A") + min(int(top_pct // 12), 25))
    return f"{band}{seq}"


def _build_sections(
    pages: list[pdf.PdfPage],
    labels: list[Any],
) -> list[dict[str, Any]]:
    """Merge real PDF layout (rects, page, text) with LLM labels (by index)."""
    sections: list[dict[str, Any]] = []
    flat_index = 0
    for page in pages:
        for seq, block in enumerate(page.blocks, start=1):
            label = labels[flat_index] if flat_index < len(labels) else None
            sections.append(
                {
                    "page_number": page.number,
                    "label": (str(label)[:100] if label else "Text"),
                    "region": _region_code(block.rect_top, seq),
                    "rect_top": block.rect_top,
                    "rect_left": block.rect_left,
                    "rect_width": block.rect_width,
                    "rect_height": block.rect_height,
                    "markdown": block.text,
                    "json_data": None,
                    "sort_order": flat_index,
                }
            )
            flat_index += 1
    return sections


async def process_job(job_id: uuid.UUID, schema: dict | None) -> None:
    settings = get_settings()
    async with get_session() as session:
        job = await repo.get_parse_job(session, job_id)
        if not job:
            return
        doc = await repo.get_document(session, job.document_id)
        if not doc:
            await repo.update_job_status(
                session, job, ParseJobStatus.FAILED, error_msg="Document not found"
            )
            return

        await repo.update_job_status(session, job, ParseJobStatus.PROCESSING)

    try:
        pages = pdf.extract_pages(doc.storage_path)
        block_texts = [b.text for page in pages for b in page.blocks]

        if not block_texts:
            raise ValueError("No extractable text found in document")

        client = ParseLLMClient(settings.vllm_base_url, settings.vllm_model)
        labels = await client.label_blocks(block_texts)
        document_json = await client.extract_document(block_texts, schema)

        sections = _build_sections(pages, labels)

        # If the model produced no usable document JSON, assemble one from the
        # real labelled content so the JSON view still reflects the document.
        if not document_json:
            document_json = _group_by_label(sections)

        markdown_output = "\n\n".join(s["markdown"] for s in sections)

        async with get_session() as session:
            job = await repo.get_parse_job(session, job_id)
            if not job:
                return
            doc = await repo.get_document(session, job.document_id)
            if doc and doc.page_count is None:
                doc.page_count = len(pages)
            await repo.create_sections_bulk(session, job_id, sections)
            await repo.update_job_status(
                session,
                job,
                ParseJobStatus.COMPLETED,
                markdown_output=markdown_output,
                json_output=document_json or None,
            )
    except Exception as exc:
        async with get_session() as session:
            job = await repo.get_parse_job(session, job_id)
            if job:
                await repo.update_job_status(
                    session, job, ParseJobStatus.FAILED, error_msg=str(exc)
                )
