from __future__ import annotations


def sanitize_surrogates(text: str) -> str:
    """Removes unpaired Unicode surrogate code points."""

    result: list[str] = []
    index = 0
    while index < len(text):
        code = ord(text[index])
        if 0xD800 <= code <= 0xDBFF:
            if index + 1 < len(text):
                next_code = ord(text[index + 1])
                if 0xDC00 <= next_code <= 0xDFFF:
                    result.append(text[index])
                    result.append(text[index + 1])
                    index += 2
                    continue
            index += 1
            continue

        if 0xDC00 <= code <= 0xDFFF:
            index += 1
            continue

        result.append(text[index])
        index += 1

    return "".join(result)
