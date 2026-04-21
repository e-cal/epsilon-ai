from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, cast

import httpx

from ..env_api_keys import get_env_api_key
from ..event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from ..models import supports_xhigh
from ..oauth import build_openai_codex_user_agent, extract_openai_codex_account_id
from ..runtime import (
    RequestAbortedError,
    create_abort_task,
    is_signal_aborted,
    maybe_await,
    raise_if_signal_aborted,
)
from ..types import (
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
    process_openai_responses_event_stream,
)
from .shared import create_empty_assistant_message, start_background_task
from .simple_options import (
    build_base_options,
    clamp_reasoning,
    coerce_stream_options,
    stream_options_to_kwargs,
)
from .sse import iterate_sse_messages

DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api"
MAX_RETRIES = 3
BASE_DELAY_MS = 1_000
CODEX_TOOL_CALL_PROVIDERS = {"openai", "openai-codex", "opencode"}
CODEX_RESPONSE_STATUSES = {
    "completed",
    "incomplete",
    "failed",
    "cancelled",
    "queued",
    "in_progress",
}


@dataclass(slots=True)
class OpenAICodexResponsesOptions(StreamOptions):
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    reasoning_summary: Literal["auto", "concise", "detailed", "off", "on"] | None = None
    service_tier: str | None = None
    text_verbosity: Literal["low", "medium", "high"] | None = None


def stream_openai_codex_responses(
    model: Model,
    context: Context,
    options: OpenAICodexResponsesOptions | StreamOptions | None = None,
):
    resolved_options = coerce_stream_options(options, OpenAICodexResponsesOptions)
    stream = create_assistant_message_event_stream()
    start_background_task(_run_openai_codex_responses(stream, model, context, resolved_options))
    return stream


async def _run_openai_codex_responses(
    stream: AssistantMessageEventStream,
    model: Model,
    context: Context,
    options: OpenAICodexResponsesOptions | None,
) -> None:
    output = create_empty_assistant_message(
        api="openai-codex-responses",
        provider=model.provider,
        model=model.id,
    )
    response: httpx.Response | None = None
    try:
        raise_if_signal_aborted(options.signal if options else None)

        api_key = options.api_key if options else None
        api_key = api_key or get_env_api_key(model.provider)
        if not api_key:
            raise ValueError(f"No API key for provider: {model.provider}")

        if options and options.transport == "websocket":
            raise NotImplementedError(
                "WebSocket transport is not implemented for openai-codex-responses"
            )

        account_id = extract_openai_codex_account_id(api_key)
        payload = build_openai_codex_responses_payload(model, context, options)
        if options and options.on_payload is not None:
            replacement = await maybe_await(options.on_payload(payload, model))
            if replacement is not None:
                payload = cast(dict[str, object], replacement)

        headers = build_openai_codex_sse_headers(
            model.headers,
            options.headers if options else None,
            account_id,
            api_key,
            options.session_id if options else None,
        )

        async with httpx.AsyncClient(timeout=None) as client:
            response = await _open_codex_stream_with_retries(
                client,
                resolve_openai_codex_url(model.base_url),
                headers,
                payload,
                options,
            )

            stream.push(StartEvent(partial=output))
            await process_openai_responses_event_stream(
                _iterate_openai_codex_response_events(
                    response, options.signal if options else None
                ),
                output,
                stream,
                model,
                options=OpenAIResponsesStreamOptions(
                    service_tier=options.service_tier if options else None,
                    resolve_service_tier=resolve_openai_codex_service_tier,
                    apply_service_tier_pricing=apply_openai_codex_service_tier_pricing,
                ),
            )

        raise_if_signal_aborted(options.signal if options else None)
        if output.stop_reason in {"error", "aborted"}:
            raise RuntimeError(output.error_message or "An unknown error occurred")

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
    finally:
        if response is not None:
            await response.aclose()


def stream_simple_openai_codex_responses(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
):
    api_key = options.api_key if options else None
    api_key = api_key or get_env_api_key(model.provider)
    if not api_key:
        raise ValueError(f"No API key for provider: {model.provider}")

    base = build_base_options(model, options, api_key)
    reasoning_effort = (
        options.reasoning
        if options and supports_xhigh(model)
        else clamp_reasoning(options.reasoning if options else None)
    )
    return stream_openai_codex_responses(
        model,
        context,
        OpenAICodexResponsesOptions(
            **stream_options_to_kwargs(base, OpenAICodexResponsesOptions),
            reasoning_effort=reasoning_effort,
        ),
    )


def build_openai_codex_responses_payload(
    model: Model,
    context: Context,
    options: OpenAICodexResponsesOptions | StreamOptions | None = None,
) -> dict[str, object]:
    resolved_options = coerce_stream_options(options, OpenAICodexResponsesOptions)
    payload: dict[str, object] = {
        "model": model.id,
        "store": False,
        "stream": True,
        "instructions": context.system_prompt,
        "input": convert_responses_messages(
            model,
            context,
            CODEX_TOOL_CALL_PROVIDERS,
            include_system_prompt=False,
        ),
        "text": {
            "verbosity": (
                resolved_options.text_verbosity
                if resolved_options and resolved_options.text_verbosity is not None
                else "medium"
            )
        },
        "include": ["reasoning.encrypted_content"],
        "prompt_cache_key": resolved_options.session_id if resolved_options else None,
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    }
    if resolved_options and resolved_options.temperature is not None:
        payload["temperature"] = resolved_options.temperature
    if resolved_options and resolved_options.service_tier is not None:
        payload["service_tier"] = resolved_options.service_tier
    if context.tools:
        payload["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": None,
            }
            for tool in context.tools
        ]
    if resolved_options and resolved_options.reasoning_effort is not None:
        payload["reasoning"] = {
            "effort": clamp_openai_codex_reasoning_effort(
                model.id, resolved_options.reasoning_effort
            ),
            "summary": resolved_options.reasoning_summary or "auto",
        }
    return payload


def get_openai_codex_service_tier_cost_multiplier(service_tier: str | None) -> float:
    if service_tier == "flex":
        return 0.5
    if service_tier == "priority":
        return 2.0
    return 1.0


def apply_openai_codex_service_tier_pricing(usage: Usage, service_tier: str | None) -> None:
    multiplier = get_openai_codex_service_tier_cost_multiplier(service_tier)
    if multiplier == 1.0:
        return
    usage.cost.input *= multiplier
    usage.cost.output *= multiplier
    usage.cost.cache_read *= multiplier
    usage.cost.cache_write *= multiplier
    usage.cost.total = (
        usage.cost.input + usage.cost.output + usage.cost.cache_read + usage.cost.cache_write
    )


def resolve_openai_codex_service_tier(
    response_service_tier: str | None,
    request_service_tier: str | None,
) -> str | None:
    """Codex responses sometimes report ``service_tier: "default"`` even when
    the request asked for ``flex`` or ``priority``. Trust the requested value
    in that case to match upstream behavior (fix(ai): trust requested Codex
    service tier, #3307)."""
    if response_service_tier == "default" and request_service_tier in {"flex", "priority"}:
        return request_service_tier
    return response_service_tier or request_service_tier


def clamp_openai_codex_reasoning_effort(model_id: str, effort: str) -> str:
    raw_id = model_id.split("/", 1)[-1]
    if raw_id.startswith(("gpt-5.2", "gpt-5.3", "gpt-5.4")) and effort == "minimal":
        return "low"
    if raw_id == "gpt-5.1" and effort == "xhigh":
        return "high"
    if raw_id == "gpt-5.1-codex-mini":
        return "high" if effort in {"high", "xhigh"} else "medium"
    return effort


def resolve_openai_codex_url(base_url: str | None) -> str:
    raw = base_url.strip() if base_url else DEFAULT_CODEX_BASE_URL
    normalized = raw.rstrip("/")
    if normalized.endswith("/codex/responses"):
        return normalized
    if normalized.endswith("/codex"):
        return f"{normalized}/responses"
    return f"{normalized}/codex/responses"


def build_openai_codex_sse_headers(
    init_headers: dict[str, str] | None,
    additional_headers: dict[str, str] | None,
    account_id: str,
    token: str,
    session_id: str | None,
) -> dict[str, str]:
    headers = {**(init_headers or {}), **(additional_headers or {})}
    headers.update(
        {
            "Authorization": f"Bearer {token}",
            "chatgpt-account-id": account_id,
            "originator": "epsilon",
            "User-Agent": build_openai_codex_user_agent(),
            "OpenAI-Beta": "responses=experimental",
            "accept": "text/event-stream",
            "content-type": "application/json",
        }
    )
    if session_id:
        headers["session_id"] = session_id
        headers["x-client-request-id"] = session_id
    return headers


async def _open_codex_stream_with_retries(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    options: OpenAICodexResponsesOptions | None,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        raise_if_signal_aborted(options.signal if options else None)
        request = client.build_request("POST", url, headers=headers, json=payload)
        try:
            response = await _send_openai_codex_request(
                client,
                request,
                options.signal if options else None,
            )
            if response.is_success:
                return response

            raw = await response.aread()
            await response.aclose()
            error_text = raw.decode("utf-8", errors="replace")
            if attempt < MAX_RETRIES and is_retryable_codex_error(response.status_code, error_text):
                await _sleep_with_abort(
                    BASE_DELAY_MS * 2**attempt, options.signal if options else None
                )
                continue

            message, friendly_message = parse_openai_codex_error_response(
                response.status_code,
                response.reason_phrase or "",
                error_text,
            )
            raise RuntimeError(friendly_message or message)
        except Exception as exc:
            if isinstance(exc, RuntimeError) and str(exc) == "Request was aborted":
                raise
            if isinstance(exc, RequestAbortedError):
                raise
            last_error = exc
            if attempt < MAX_RETRIES and not _is_usage_limit_error_message(str(exc)):
                await _sleep_with_abort(
                    BASE_DELAY_MS * 2**attempt, options.signal if options else None
                )
                continue
            raise
    raise RuntimeError(str(last_error) if last_error is not None else "Failed after retries")


async def _iterate_openai_codex_response_events(
    response: httpx.Response,
    signal: object | None,
) -> AsyncIterator[dict[str, object]]:
    async for _event_name, data in iterate_sse_messages(response, signal):
        if not data or data == "[DONE]":
            continue
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            continue
        event_type = cast(str | None, parsed.get("type"))
        if event_type == "error":
            error = cast(dict[str, object], parsed.get("error") or {})
            code = cast(str | None, error.get("code") or parsed.get("code"))
            message = cast(str | None, error.get("message") or parsed.get("message"))
            raise RuntimeError(f"Codex error: {message or code or json.dumps(parsed)}")

        if event_type == "response.failed":
            response_payload = cast(dict[str, object], parsed.get("response") or {})
            error = cast(dict[str, object], response_payload.get("error") or {})
            message = cast(str | None, error.get("message"))
            raise RuntimeError(message or "Codex response failed")

        if event_type in {"response.done", "response.completed", "response.incomplete"}:
            response_payload = cast(dict[str, object], parsed.get("response") or {})
            normalized = dict(response_payload)
            status = normalize_openai_codex_status(normalized.get("status"))
            if status is None:
                normalized.pop("status", None)
            else:
                normalized["status"] = status
            yield {"type": "response.completed", "response": normalized}
            return

        yield cast(dict[str, object], parsed)


def normalize_openai_codex_status(status: object) -> str | None:
    if not isinstance(status, str):
        return None
    return status if status in CODEX_RESPONSE_STATUSES else None


def is_retryable_codex_error(status: int, error_text: str) -> bool:
    if status in {429, 500, 502, 503, 504}:
        return True
    return bool(
        re.search(
            r"rate.?limit|overloaded|service.?unavailable|upstream.?connect|connection.?refused",
            error_text,
            re.IGNORECASE,
        )
    )


def parse_openai_codex_error_response(
    status_code: int,
    status_text: str,
    raw: str,
) -> tuple[str, str | None]:
    message = raw or status_text or "Request failed"
    friendly_message: str | None = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return message, friendly_message

    if not isinstance(parsed, dict):
        return message, friendly_message
    error = cast(dict[str, object], parsed.get("error") or {})
    if not error:
        return message, friendly_message

    code = cast(str, error.get("code") or error.get("type") or "")
    if (
        re.search(
            r"usage_limit_reached|usage_not_included|rate_limit_exceeded", code, re.IGNORECASE
        )
        or status_code == 429
    ):
        plan = cast(str | None, error.get("plan_type"))
        plan_suffix = f" ({plan.lower()} plan)" if plan else ""
        resets_at = error.get("resets_at")
        if isinstance(resets_at, int | float):
            minutes = max(0, round((resets_at * 1000 - _now_ms()) / 60_000))
            retry_hint = f" Try again in ~{minutes} min."
        else:
            retry_hint = ""
        friendly_message = (
            f"You have hit your ChatGPT usage limit{plan_suffix}.{retry_hint}".strip()
        )

    raw_message = cast(str | None, error.get("message"))
    return raw_message or friendly_message or message, friendly_message


async def _sleep_with_abort(delay_ms: int, signal: object | None) -> None:
    raise_if_signal_aborted(signal)
    sleep_task = asyncio.create_task(asyncio.sleep(delay_ms / 1000))
    abort_task = create_abort_task(signal)
    if abort_task is None:
        await sleep_task
        return

    try:
        done, _pending = await asyncio.wait(
            {sleep_task, abort_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if abort_task in done:
            sleep_task.cancel()
            await asyncio.gather(sleep_task, return_exceptions=True)
            raise RequestAbortedError("Request was aborted")
        await sleep_task
    finally:
        abort_task.cancel()
        await asyncio.gather(abort_task, return_exceptions=True)


async def _send_openai_codex_request(
    client: httpx.AsyncClient,
    request: httpx.Request,
    signal: object | None,
) -> httpx.Response:
    send_task = asyncio.create_task(client.send(request, stream=True))
    abort_task = create_abort_task(signal)
    if abort_task is None:
        return await send_task

    try:
        done, _pending = await asyncio.wait(
            {send_task, abort_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if abort_task in done:
            send_task.cancel()
            await asyncio.gather(send_task, return_exceptions=True)
            raise RequestAbortedError("Request was aborted")
        return await send_task
    finally:
        abort_task.cancel()
        await asyncio.gather(abort_task, return_exceptions=True)


def _is_usage_limit_error_message(message: str) -> bool:
    return "usage limit" in message.lower()


def _is_abort_error(exc: Exception, options: OpenAICodexResponsesOptions | None) -> bool:
    signal = options.signal if options else None
    return isinstance(exc, RequestAbortedError) or is_signal_aborted(signal)


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
