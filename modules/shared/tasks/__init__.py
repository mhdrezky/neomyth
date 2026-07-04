"""Reusable document-processing tasks.

Each task is a pure orchestration step usable by any module: clients and
prompts are passed in by the caller, results are returned as plain data.
"""

from modules.shared.tasks.image_to_markdown import image_to_markdown
from modules.shared.tasks.markdown_to_json import markdown_to_json
from modules.shared.tasks.pdf_to_markdown import pdf_text_to_markdown

__all__ = ["image_to_markdown", "markdown_to_json", "pdf_text_to_markdown"]
