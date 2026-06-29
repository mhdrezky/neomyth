"""PDF text-layout extraction and page rendering via PyMuPDF.

Coordinates are returned as percentages of the page size so the frontend can
overlay source-grounding rectangles regardless of render resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz  # PyMuPDF


@dataclass
class TextBlock:
    """A paragraph-level text block with its bounding box (in % of page)."""

    text: str
    rect_top: float
    rect_left: float
    rect_width: float
    rect_height: float


@dataclass
class PdfPage:
    number: int  # 1-based
    width: float  # points
    height: float  # points
    blocks: list[TextBlock] = field(default_factory=list)


def extract_pages(path: str) -> list[PdfPage]:
    """Extract paragraph-level text blocks with bounding boxes from every page."""
    pages: list[PdfPage] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            pw = page.rect.width or 1.0
            ph = page.rect.height or 1.0
            blocks: list[TextBlock] = []
            for raw in page.get_text("blocks"):
                # raw: (x0, y0, x1, y1, text, block_no, block_type)
                x0, y0, x1, y1, text, _block_no, block_type = raw
                if block_type != 0:
                    continue  # skip image blocks
                cleaned = (text or "").strip()
                if not cleaned:
                    continue
                blocks.append(
                    TextBlock(
                        text=cleaned,
                        rect_top=round(y0 / ph * 100, 3),
                        rect_left=round(x0 / pw * 100, 3),
                        rect_width=round((x1 - x0) / pw * 100, 3),
                        rect_height=round((y1 - y0) / ph * 100, 3),
                    )
                )
            blocks.sort(key=lambda b: (b.rect_top, b.rect_left))
            pages.append(PdfPage(number=index + 1, width=pw, height=ph, blocks=blocks))
    return pages


def page_count(path: str) -> int:
    with fitz.open(path) as doc:
        return doc.page_count


def render_page_png(path: str, page_number: int, zoom: float = 2.0) -> bytes:
    """Render a 1-based page to PNG bytes."""
    with fitz.open(path) as doc:
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Page {page_number} out of range (1..{doc.page_count})")
        page = doc[page_number - 1]
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png")


def plain_text(pages: list[PdfPage]) -> str:
    """Flatten all pages' blocks into a single text string for LLM input."""
    chunks: list[str] = []
    for page in pages:
        for block in page.blocks:
            chunks.append(block.text)
    return "\n\n".join(chunks)
