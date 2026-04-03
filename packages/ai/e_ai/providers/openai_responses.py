from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, cast

import httpx

from ..env_api_keys import get_env_api_key
from ..event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from ..runtime import RequestAbortedError, is_signal_aborted, maybe_await, raise_if_signal_aborted
from ..types import (
    CacheRetention,
    Context,
    DoneEvent,
    ErrorEvent,
    Model,
    SimpleStreamOptions,
    StartEvent,
    StreamOptions,
    Usage,
)
from .openai_responses_shared import (
    OpenAIResponsesStreamOptions,
    convert_responses_messages,
    convert_responses_tools,
    process_openai_responses_event_stream,
)
from .shared import create_empty_assistant_message, start_background_task
from .simple_options import build_base_options, clamp_reasoning
from .sse import iterate_sse_messages

OPENAI_TOOL_CALL_PROVIDERS = {"openai"}


@dataclass(slots=True)
class OpenAIResponsesOptions(StreamOptions):
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None
    service_tier: str | None = None


def stream_openai_responses(
    model: Model,
    context: Context,
    options: OpenAIResponsesOptions | None = None,
):
    stream = create_assistant_message_event_stream()
    start_background_task(_run_openai_responses(stream, model, context, options))
    return stream


async def _run_openai_responses(
    stream: AssistantMessageEventStream,
    model: Model,
    context: Context,
    options: OpenAIResponsesOptions | None,
) -> None:
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    try:
        raise_if_signal_aborted(options.signal if options else None)

        api_key = options.api_key if options else None
        api_key = api_key or get_env_api_key(model.provider)
        if not api_key:
            raise ValueError("OpenAI API key is required")

        payload = build_openai_responses_payload(model, context, options)
        if options and options.on_payload is not None:
            replacement = await maybe_await(options.on_payload(payload, model))
            if replacement is not None:
                payload = cast(dict[str, object], replacement)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(model.headers or {}),
            **(options.headers if options and options.headers else {}),
        }
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "POST",
                f"{model.base_url.rstrip('/')}/responses",
                headers=headers,
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            stream.push(StartEvent(partial=output))
            await process_openai_responses_event_stream(
                _iterate_openai_response_events(response, options.signal if options else None),
                output,
                stream,
                model,
                options=OpenAIResponsesStreamOptions(
                    service_tier=options.service_tier if options else None,
                    apply_service_tier_pricing=apply_service_tier_pricing,
                ),
            )

        raise_if_signal_aborted(options.signal if options else None)
        if output.stop_reason in {"error", "aborted"}:
            raise RuntimeError("An unknown error occurred")

        stream.push(
            DoneEvent(
                reason=cast(Literal["stop", "length", "toolUse"], output.stop_reason),
                message=output,
            )
        )
        stream.end(output)
    except Exception as exc:
        output.stop_reason = "aborted" if _is_abort_error(exc, options) else "error"
        output.error_message = str(exc)
        stream.push(
            ErrorEvent(
                reason=cast(Literal["aborted", "error"], output.stop_reason),
                error=output,
            )
        )
        stream.end(output)


def stream_simple_openai_responses(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
):
    api_key = options.api_key if options else None
    api_key = api_key or get_env_api_key(model.provider)
    if not api_key:
        raise ValueError(f"No API key for provider: {model.provider}")

    base = build_base_options(model, options, api_key)
    reasoning_effort = options.reasoning if options and model.reasoning else None
    if reasoning_effort is not None and not model.id.startswith("gpt-5."):
        reasoning_effort = clamp_reasoning(reasoning_effort)

    return stream_openai_responses(
        model,
        context,
        OpenAIResponsesOptions(**base.__dict__, reasoning_effort=reasoning_effort),
    )


def build_openai_responses_payload(
    model: Model,
    context: Context,
    options: OpenAIResponsesOptions | None = None,
) -> dict[str, object]:
    cache_retention = _resolve_cache_retention(options.cache_retention if options else None)
    payload: dict[str, object] = {
        "model": model.id,
        "input": convert_responses_messages(model, context, OPENAI_TOOL_CALL_PROVIDERS),
        "stream": True,
        "store": False,
    }
    if options and options.session_id and cache_retention != "none":
        payload["prompt_cache_key"] = options.session_id
        prompt_cache_retention = _get_prompt_cache_retention(model.base_url, cache_retention)
        if prompt_cache_retention is not None:
            payload["prompt_cache_retention"] = prompt_cache_retention
    if options and options.max_tokens is not None:
        payload["max_output_tokens"] = options.max_tokens
    if options and options.temperature is not None:
        payload["temperature"] = options.temperature
    if options and options.service_tier is not None:
        payload["service_tier"] = options.service_tier
    if context.tools:
        payload["tools"] = convert_responses_tools(context.tools)
    if model.reasoning:
        if options and (options.reasoning_effort or options.reasoning_summary):
            payload["reasoning"] = {
                "effort": options.reasoning_effort or "medium",
                "summary": options.reasoning_summary or "auto",
            }
            payload["include"] = ["reasoning.encrypted_content"]
        else:
            payload["reasoning"] = {"effort": "none"}
    return payload


async def _iterate_openai_response_events(
    response: httpx.Response,
    signal: object | None,
) -> AsyncIterator[dict[str, object]]:
    async for _event_name, data in iterate_sse_messages(response, signal):
        if not data or data == "[DONE]":
            continue
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            yield cast(dict[str, object], parsed)


def get_service_tier_cost_multiplier(service_tier: str | None) -> float:
    if service_tier == "flex":
        return 0.5
    if service_tier == "priority":
        return 2.0
    return 1.0


def apply_service_tier_pricing(usage: Usage, service_tier: str | None) -> None:
    multiplier = get_service_tier_cost_multiplier(service_tier)
    if multiplier == 1.0:
        return
    usage.cost.input *= multiplier
    usage.cost.output *= multiplier
    usage.cost.cache_read *= multiplier
    usage.cost.cache_write *= multiplier
    usage.cost.total = (
        usage.cost.input + usage.cost.output + usage.cost.cache_read + usage.cost.cache_write
    )


def _resolve_cache_retention(cache_retention: CacheRetention | None) -> CacheRetention:
    if cache_retention is not None:
        return cache_retention
    if os.environ.get("PI_CACHE_RETENTION") == "long":
        return "long"
    return "short"


def _get_prompt_cache_retention(base_url: str, cache_retention: CacheRetention) -> str | None:
    if cache_retention != "long":
        return None
    if "api.openai.com" in base_url:
        return "24h"
    return None


def _is_abort_error(exc: Exception, options: OpenAIResponsesOptions | None) -> bool:
    signal = options.signal if options else None
    return isinstance(exc, RequestAbortedError) or is_signal_aborted(signal)
