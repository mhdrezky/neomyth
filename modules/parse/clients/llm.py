"""OpenAI-compatible client for document structure extraction via vLLM.

The target container has a small total context window and runs a small model,
so this client keeps every call narrow and focused:
  - label_blocks: one short classification per block (reliable on small models)
  - extract_document: a single schema-filling call over the concatenated text

Section markdown always comes from the real extracted text, never the model.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from modules.shared.constants import (
    CHARS_PER_TOKEN,
    MODEL_MAX_CONTEXT,
    PARSE_MIN_OUTPUT_TOKENS,
)

_LABEL_SYSTEM = (
    "Classify the document section. Reply with ONLY a 1-3 word label such as: "
    "Header, Bill To, Line Item, Totals, Notes, Footer, Table, Paragraph."
)
_DOC_SYSTEM = (
    "Extract data from the document into JSON. If a schema is given, match its "
    "shape. Reply with ONLY the JSON object."
)

_LABEL_CONCURRENCY = 8


def _clean_label(raw: str | None) -> str:
    if not raw:
        return "Text"
    first = raw.strip().splitlines()[0].strip().strip("\"'.:")
    words = first.split()
    label = " ".join(words[:3]) if words else "Text"
    return label[:100] or "Text"


class ParseLLMClient:
    def __init__(self, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
        self._model = model

    async def label_blocks(self, blocks: list[str]) -> list[str]:
        """Return one cleaned label per block (best effort, order-preserving)."""
        sem = asyncio.Semaphore(_LABEL_CONCURRENCY)

        async def one(text: str) -> str:
            async with sem:
                try:
                    resp = await self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": _LABEL_SYSTEM},
                            {"role": "user", "content": text[:600]},
                        ],
                        max_tokens=12,
                        temperature=0.0,
                    )
                    return _clean_label(resp.choices[0].message.content)
                except Exception:
                    return "Text"

        return await asyncio.gather(*(one(b) for b in blocks))

    async def extract_document(
        self,
        blocks: list[str],
        schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Single focused call to fill the schema. Returns {} on failure."""
        schema_part = f"Schema: {json.dumps(schema)}\n\n" if schema else ""
        body = "\n".join(blocks)

        budget_chars = (
            MODEL_MAX_CONTEXT - PARSE_MIN_OUTPUT_TOKENS - 96
        ) * CHARS_PER_TOKEN - len(schema_part) - len(_DOC_SYSTEM)
        if len(body) > budget_chars:
            body = body[: max(0, budget_chars)]

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _DOC_SYSTEM},
                    {"role": "user", "content": f"{schema_part}Document:\n{body}"},
                ],
                max_tokens=PARSE_MIN_OUTPUT_TOKENS,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def health(self) -> bool:
        try:
            models = await self._client.models.list()
            return len(models.data) > 0
        except Exception:
            return False
