"""Extract and validate the forced-decision JSON from a model response."""

from __future__ import annotations

import json
import re


_SMART_QUOTES = str.maketrans({
    "“": '"', "”": '"',  # “ ”
    "‘": "'", "’": "'",  # ‘ ’
})


def extract_json(text: str) -> dict | None:
    """Return the first balanced top-level JSON object found in the text."""
    if not text:
        return None
    # Strip common markdown fences first.
    text = re.sub(r"```(?:json)?", "", text)
    # Some models (observed: Claude) occasionally auto-typeset a straight "
    # into a curly closing quote mid-string. json.loads requires the ASCII
    # form to terminate a string, so a stray curly quote makes the brace
    # scanner below think the string never closes and the whole object is
    # unparseable. Danish prompts/schemas never require curly quotes as
    # meaningful JSON syntax, so normalizing is safe.
    text = text.translate(_SMART_QUOTES)
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    return None


def validate(parsed: dict | None, output_schema: dict) -> tuple[dict, list[str]]:
    """Coerce fields to schema types; return (clean_fields, errors)."""
    errors: list[str] = []
    clean: dict = {}
    if parsed is None:
        return clean, ["no_json_found"]

    for name, spec in output_schema.items():
        value = parsed.get(name)
        kind = spec["type"]
        if value is None:
            errors.append(f"missing:{name}")
            continue
        if kind == "numeric":
            try:
                num = float(value)
            except (TypeError, ValueError):
                errors.append(f"not_numeric:{name}")
                continue
            if not (spec["min"] <= num <= spec["max"]):
                errors.append(f"out_of_range:{name}={num}")
                continue
            clean[name] = num
        elif kind == "boolean":
            if isinstance(value, bool):
                clean[name] = value
            elif isinstance(value, str) and value.lower() in ("true", "false", "ja", "nej"):
                clean[name] = value.lower() in ("true", "ja")
            else:
                errors.append(f"not_boolean:{name}")
        elif kind == "categorical":
            if isinstance(value, str) and value.strip().lower() in spec["values"]:
                clean[name] = value.strip().lower()
            else:
                errors.append(f"invalid_category:{name}={value!r}")
        elif kind == "text":
            clean[name] = str(value)
    return clean, errors
