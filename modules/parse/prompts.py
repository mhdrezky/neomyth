"""Prompt definitions for the parse module.

Prompts stay module-local by design; shared clients/tasks receive them as
arguments so other modules can bring their own.
"""

LABEL_SYSTEM = (
    "Classify the document section. Reply with ONLY a 1-3 word label such as: "
    "Header, Bill To, Line Item, Totals, Notes, Footer, Table, Paragraph."
)

DOC_SYSTEM = (
    "Extract data from the markdown document into a single JSON object. "
    "If a JSON Schema (draft-07) is given, the output MUST conform to it: "
    "respect types, required fields, and enums; use null for values absent "
    "from the document; keep numbers as numbers and dates as ISO-8601 strings. "
    "If a plain example object is given instead, match its shape. "
    "Never invent values that are not in the document. "
    "Reply with ONLY the JSON object."
)

REPAIR_SYSTEM = (
    "You previously extracted JSON from a document, but it failed JSON Schema "
    "(draft-07) validation. Fix ONLY the reported problems using the document "
    "content; keep every valid field unchanged. Reply with ONLY the corrected "
    "JSON object."
)

VISION_SYSTEM = (
    "You transcribe scanned document pages into GitHub-flavored Markdown. "
    "Preserve reading order, headings, lists, and tables. Transcribe text "
    "exactly as printed; do not summarize, translate, or invent content. "
    "Output ONLY the markdown."
)

VISION_USER = "Transcribe this page to markdown."
