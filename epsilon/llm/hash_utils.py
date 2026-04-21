from __future__ import annotations


def short_hash(value: str) -> str:
    """Fast deterministic hash to shorten long strings."""

    h1 = 0xDEADBEEF
    h2 = 0x41C6CE57
    for char in value:
        code = ord(char)
        h1 = _imul(h1 ^ code, 2654435761)
        h2 = _imul(h2 ^ code, 1597334677)

    h1 = _imul(h1 ^ (h1 >> 16), 2246822507) ^ _imul(h2 ^ (h2 >> 13), 3266489909)
    h2 = _imul(h2 ^ (h2 >> 16), 2246822507) ^ _imul(h1 ^ (h1 >> 13), 3266489909)
    return _to_base36(h2 & 0xFFFFFFFF) + _to_base36(h1 & 0xFFFFFFFF)


def _imul(a: int, b: int) -> int:
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


def _to_base36(value: int) -> str:
    if value == 0:
        return "0"

    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result: list[str] = []
    remaining = value
    while remaining:
        remaining, digit = divmod(remaining, 36)
        result.append(digits[digit])
    return "".join(reversed(result))
