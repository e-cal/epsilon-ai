from __future__ import annotations

from ..types import Model, SimpleStreamOptions, StreamOptions, ThinkingLevel


def build_base_options(
    model: Model,
    options: SimpleStreamOptions | None = None,
    api_key: str | None = None,
) -> StreamOptions:
    max_tokens = min(model.max_tokens, 32_000)
    if options and options.max_tokens:
        max_tokens = options.max_tokens

    return StreamOptions(
        temperature=options.temperature if options else None,
        max_tokens=max_tokens,
        signal=options.signal if options else None,
        api_key=api_key or (options.api_key if options else None),
        cache_retention=options.cache_retention if options else None,
        session_id=options.session_id if options else None,
        headers=options.headers if options else None,
        on_payload=options.on_payload if options else None,
        max_retry_delay_ms=options.max_retry_delay_ms if options else None,
        metadata=options.metadata if options else None,
    )


def clamp_reasoning(effort: ThinkingLevel | None) -> ThinkingLevel | None:
    if effort == "xhigh":
        return "high"
    return effort


def adjust_max_tokens_for_thinking(
    base_max_tokens: int,
    model_max_tokens: int,
    reasoning_level: ThinkingLevel,
    custom_budgets: dict[ThinkingLevel, int] | None = None,
) -> tuple[int, int]:
    budgets: dict[str, int] = {
        "minimal": 1_024,
        "low": 2_048,
        "medium": 8_192,
        "high": 16_384,
    }
    if custom_budgets:
        for level in ("minimal", "low", "medium", "high"):
            value = custom_budgets.get(level)  # type: ignore[arg-type]
            if value is not None:
                budgets[level] = value

    level = clamp_reasoning(reasoning_level) or "medium"
    thinking_budget = budgets[level]
    max_tokens = min(base_max_tokens + thinking_budget, model_max_tokens)

    min_output_tokens = 1_024
    if max_tokens <= thinking_budget:
        thinking_budget = max(0, max_tokens - min_output_tokens)

    return max_tokens, thinking_budget
