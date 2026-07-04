"""Task: PDF text pages → per-page GitHub-flavored markdown (pymupdf4llm)."""

from __future__ import annotations

import pymupdf4llm


def pdf_text_to_markdown(path: str, page_numbers: list[int]) -> dict[int, str]:
    """Per-page markdown for the given 1-based pages of a text-layer PDF.

    Uses pymupdf4llm (heading detection from font sizes, table extraction).
    Returns {} on failure so callers can fall back to raw block text.
    """
    if not page_numbers:
        return {}
    try:
        chunks = pymupdf4llm.to_markdown(
            path,
            pages=[n - 1 for n in page_numbers],
            page_chunks=True,
            show_progress=False,
        )
        return {
            number: (chunk.get("text") or "").strip()
            for number, chunk in zip(page_numbers, chunks)
        }
    except Exception:
        return {}
