"""JSON Schema (draft-07) helpers for schema-guided extraction.

Two schema styles are accepted from callers:
  - a real JSON Schema (draft-07): validated here and enforced on the output
  - a plain example object ("shape hint"): passed to the LLM as-is, no validation
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, FormatChecker
from jsonschema.exceptions import SchemaError

_SCHEMA_MARKER_KEYS = {"$schema", "type", "properties", "items", "required", "definitions", "$defs"}


def is_json_schema(candidate: Any) -> bool:
    """Heuristic: does this dict look like a JSON Schema rather than an example?"""
    return isinstance(candidate, dict) and bool(_SCHEMA_MARKER_KEYS & candidate.keys())


def check_schema(schema: dict[str, Any]) -> None:
    """Raise ValueError if the schema is not a valid draft-07 JSON Schema."""
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid draft-07 JSON Schema: {exc.message}") from exc


def validate_output(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate extracted data against a draft-07 schema; return error messages."""
    # FormatChecker makes "format" assertive (draft-07 treats it as annotation
    # by default) so e.g. {"format": "email"} is actually enforced.
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path}: {err.message}")
    return errors
