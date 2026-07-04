"""Parse pipeline: PDF → per-page markdown (stage 1) → validated JSON (stage 2).

Per-page routing: pages with a usable text layer go through PyMuPDF
(pymupdf4llm markdown); image-only scanned pages are rendered to PNG and
transcribed by the multimodal vLLM worker. Extracted JSON is validated against
the draft-07 schema when one is provided, with a bounded repair loop.

Stages and clients are the reusable ones from modules/shared; only the prompts
(modules/parse/prompts.py) and section grounding are parse-specific.

Runs in the background after a job is created. Opens its own DB session so it
is independent of the request lifecycle.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from api.config import get_settings
from modules.parse import pdf, prompts, repository as repo
from modules.shared.clients import TextLLMClient, VisionLLMClient
from modules.shared.constants import PARSE_VISION_RENDER_ZOOM
from modules.shared.db import get_session
from modules.shared.db.models import ParseJobStatus
from modules.shared.tasks import (
    image_to_markdown,
    markdown_to_json,
    pdf_text_to_markdown,
)

_LABEL_CONCURRENCY = 8
_LABEL_MAX_TOKENS = 12


def _clean_label(raw: str | None) -> str:
    if not raw:
        return "Text"
    first = raw.strip().splitlines()[0].strip().strip("\"'.:")
    words = first.split()
    label = " ".join(words[:3]) if words else "Text"
    return label[:100] or "Text"


async def _label_blocks(client: TextLLMClient, blocks: list[str]) -> list[str]:
    """Return one cleaned label per block (best effort, order-preserving)."""
    sem = asyncio.Semaphore(_LABEL_CONCURRENCY)

    async def one(text: str) -> str:
        async with sem:
            try:
                raw = await client.complete(
                    prompts.LABEL_SYSTEM, text[:600], max_tokens=_LABEL_MAX_TOKENS
                )
                return _clean_label(raw)
            except Exception:
                return "Text"

    return await asyncio.gather(*(one(b) for b in blocks))


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
    scanned_markdown: dict[int, str],
) -> list[dict[str, Any]]:
    """Merge real PDF layout with LLM labels; scanned pages become one
    full-page section holding the vision transcription."""
    sections: list[dict[str, Any]] = []
    label_index = 0
    sort_order = 0
    for page in pages:
        if page.number in scanned_markdown:
            sections.append(
                {
                    "page_number": page.number,
                    "label": "Scanned Page",
                    "region": "A1",
                    "rect_top": 0.0,
                    "rect_left": 0.0,
                    "rect_width": 100.0,
                    "rect_height": 100.0,
                    "markdown": scanned_markdown[page.number],
                    "json_data": None,
                    "sort_order": sort_order,
                }
            )
            sort_order += 1
            continue
        for seq, block in enumerate(page.blocks, start=1):
            label = labels[label_index] if label_index < len(labels) else None
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
                    "sort_order": sort_order,
                }
            )
            label_index += 1
            sort_order += 1
    return sections


async def _stage1_markdown(
    storage_path: str,
    pages: list[pdf.PdfPage],
    vision: VisionLLMClient,
) -> tuple[dict[int, str], dict[int, str]]:
    """Stage 1: one markdown string per page.

    Returns (page_markdown, scanned_markdown) — the second maps only the
    scanned pages, so section building knows which pages came from vision.
    """
    text_pages = [p for p in pages if not p.is_scanned]
    scanned_pages = [p for p in pages if p.is_scanned]

    page_markdown: dict[int, str] = {}

    # Text-dominant pages → PyMuPDF markdown (headings, tables), with a
    # fallback to raw block text if pymupdf4llm fails.
    md_by_page = await asyncio.to_thread(
        pdf_text_to_markdown, storage_path, [p.number for p in text_pages]
    )
    for page in text_pages:
        md = md_by_page.get(page.number, "")
        page_markdown[page.number] = md or "\n\n".join(b.text for b in page.blocks)

    # Scanned pages → render PNG, transcribe via the multimodal worker.
    scanned_markdown: dict[int, str] = {}
    for page in scanned_pages:
        png = await asyncio.to_thread(
            pdf.render_page_png, storage_path, page.number, PARSE_VISION_RENDER_ZOOM
        )
        try:
            md = await image_to_markdown(
                vision,
                png,
                system_prompt=prompts.VISION_SYSTEM,
                user_prompt=prompts.VISION_USER,
            )
        except Exception as exc:
            raise ValueError(
                f"Vision transcription failed on page {page.number}: {exc}"
            ) from exc
        scanned_markdown[page.number] = md
        page_markdown[page.number] = md

    return page_markdown, scanned_markdown


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
        # Inline schema (editor) wins; otherwise load the stored schema by id.
        if schema is None and job.schema_id:
            stored = await repo.get_schema(session, job.schema_id)
            schema = stored.content if stored else None

        await repo.update_job_status(session, job, ParseJobStatus.PROCESSING)

    try:
        pages = await asyncio.to_thread(pdf.extract_pages, doc.storage_path)
        if not pages:
            raise ValueError("Document has no pages")

        # One multimodal worker serves both text and vision calls.
        llm = TextLLMClient(settings.vllm_base_url, settings.vllm_model)
        vision = VisionLLMClient(settings.vllm_base_url, settings.vllm_model)

        page_markdown, scanned_markdown = await _stage1_markdown(
            doc.storage_path, pages, vision
        )
        markdown_output = "\n\n".join(
            page_markdown[p.number] for p in pages if page_markdown.get(p.number)
        )
        if not markdown_output.strip():
            raise ValueError("No extractable content found in document")

        text_block_texts = [
            b.text for p in pages if not p.is_scanned for b in p.blocks
        ]
        labels = await _label_blocks(llm, text_block_texts)
        sections = _build_sections(pages, labels, scanned_markdown)

        document_json, validation_errors = await markdown_to_json(
            llm,
            markdown_output,
            schema,
            system_prompt=prompts.DOC_SYSTEM,
            repair_system_prompt=prompts.REPAIR_SYSTEM,
        )
        if validation_errors:
            # Surface remaining problems in the JSON view instead of hiding them.
            document_json["_validation_errors"] = validation_errors[:10]

        # If the model produced no usable document JSON, assemble one from the
        # real labelled content so the JSON view still reflects the document.
        if not document_json:
            document_json = _group_by_label(sections)

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
