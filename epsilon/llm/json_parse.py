from __future__ import annotations

import json
from typing import Any


def parse_streaming_json(partial_json: str | None) -> dict[str, Any]:
    """Best-effort parser for incomplete streaming JSON objects."""

    if not partial_json or not partial_json.strip():
        return {}

    parsed = _try_parse(partial_json)
    if isinstance(parsed, dict):
        return parsed

    repaired = _repair_partial_json(partial_json)
    if repaired is None:
        return {}

    parsed = _try_parse(repaired)
    return parsed if isinstance(parsed, dict) else {}


def _try_parse(value: str) -> Any | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _repair_partial_json(value: str) -> str | None:
    text = value.rstrip()
    if not text:
        return None

    stack: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in {"}", "]"} and stack and stack[-1] == char:
            stack.pop()

    if escaped:
        text = text[:-1]
    if in_string:
        text += '"'

    text = _trim_incomplete_suffix(text)
    if text is None:
        return None

    return text + "".join(reversed(stack))


def _trim_incomplete_suffix(value: str) -> str | None:
    text = value.rstrip()
    if not text:
        return None

    while text:
        last = text[-1]
        if last == ",":
            text = text[:-1].rstrip()
            continue
        if last == ":":
            text = f"{text} null"
            break
        break

    return text or None
