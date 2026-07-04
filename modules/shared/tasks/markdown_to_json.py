"""Task: markdown document → JSON, validated against draft-07 when applicable.

Returns (data, errors): validation errors that survived the repair loop are
returned to the caller, which decides how to surface them.
"""

from __future__ import annotations

import json
from typing import Any

from modules.shared.clients.llm import TextLLMClient
from modules.shared.constants import (
    CHARS_PER_TOKEN,
    MODEL_MAX_CONTEXT,
    PARSE_JSON_REPAIR_ATTEMPTS,
    PARSE_LLM_TEMPERATURE,
    PARSE_OUTPUT_RESERVE_TOKENS,
)
from modules.shared.utils.json_schema import is_json_schema, validate_output

_PROMPT_MARGIN_TOKENS = 96


def _fit_body(body: str, overhead: str) -> str:
    """Truncate the document body, always leaving the minimum output reserve."""
    budget_chars = (
        MODEL_MAX_CONTEXT - PARSE_OUTPUT_RESERVE_TOKENS - _PROMPT_MARGIN_TOKENS
    ) * CHARS_PER_TOKEN - len(overhead)
    if len(body) > budget_chars:
        body = body[: max(0, budget_chars)]
    return body


def _output_budget(prompt_chars: int) -> int:
    """Dynamic max_tokens: everything left in the window after the prompt.

    CHARS_PER_TOKEN is a conservative (low) estimate, so the prompt-token
    guess overshoots and prompt + max_tokens stays within the model window.
    """
    est_prompt_tokens = prompt_chars // CHARS_PER_TOKEN + _PROMPT_MARGIN_TOKENS
    return max(PARSE_OUTPUT_RESERVE_TOKENS, MODEL_MAX_CONTEXT - est_prompt_tokens)


async def markdown_to_json(
    client: TextLLMClient,
    markdown: str,
    schema: dict[str, Any] | None,
    *,
    system_prompt: str,
    repair_system_prompt: str | None = None,
    repair_attempts: int = PARSE_JSON_REPAIR_ATTEMPTS,
    temperature: float = PARSE_LLM_TEMPERATURE,
) -> tuple[dict[str, Any], list[str]]:
    """Fill the schema from markdown; repair draft-07 violations if possible."""
    schema_part = f"Schema: {json.dumps(schema)}\n\n" if schema else ""
    body = _fit_body(markdown, schema_part + system_prompt)
    user = f"{schema_part}Document:\n{body}"
    data = await client.complete_json(
        system_prompt,
        user,
        max_tokens=_output_budget(len(system_prompt) + len(user)),
        temperature=temperature,
    )

    if not (schema and is_json_schema(schema)):
        return data, []

    errors = validate_output(data, schema)
    attempts = 0
    while errors and repair_system_prompt and attempts < repair_attempts:
        context = (
            f"Schema: {json.dumps(schema)}\n\n"
            f"Previous JSON: {json.dumps(data)}\n\n"
            f"Validation errors:\n" + "\n".join(f"- {e}" for e in errors[:8]) + "\n\n"
        )
        body = _fit_body(markdown, context + repair_system_prompt)
        user = f"{context}Document:\n{body}"
        repaired = await client.complete_json(
            repair_system_prompt,
            user,
            max_tokens=_output_budget(len(repair_system_prompt) + len(user)),
            temperature=temperature,
        )
        if repaired:
            data = repaired
        errors = validate_output(data, schema)
        attempts += 1

    return data, errors
