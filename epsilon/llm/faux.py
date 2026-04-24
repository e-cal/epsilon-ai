from __future__ import annotations

import asyncio
import json
import math
import random
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal, cast

from .api_registry import ApiProvider, register_api_provider, unregister_api_provider
from .event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from .json_parse import parse_streaming_json
from .models import register_models, unregister_provider_models
from .providers.shared import start_background_task
from .runtime import (
    RequestAbortedError,
    create_abort_task,
    is_signal_aborted,
    maybe_await,
    raise_if_signal_aborted,
)
from .types import (
    AssistantMessage,
    Context,
    DoneEvent,
    ErrorEvent,
    ImageContent,
    JSONObject,
    Message,
    Model,
    StartEvent,
    StopReason,
    StreamOptions,
    TextContent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingContent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCall,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultMessage,
    Usage,
)

DEFAULT_API = "faux"
DEFAULT_PROVIDER = "faux"
DEFAULT_MODEL_ID = "faux-1"
DEFAULT_MODEL_NAME = "Faux Model"
DEFAULT_BASE_URL = "http://localhost:0"
DEFAULT_MIN_TOKEN_SIZE = 3
DEFAULT_MAX_TOKEN_SIZE = 5


@dataclass(slots=True)
class FauxModelDefinition:
    id: str
    name: str | None = None
    reasoning: bool = False
    input: list[str] = field(default_factory=lambda: ["text", "image"])
    cost_input: float = 0.0
    cost_output: float = 0.0
    cost_cache_read: float = 0.0
    cost_cache_write: float = 0.0
    context_window: int = 128_000
    max_tokens: int = 16_384


type FauxResponseFactory = Callable[
    [Context, StreamOptions | None, "FauxProviderState", Model],
    AssistantMessage | Awaitable[AssistantMessage],
]
type FauxResponseStep = AssistantMessage | FauxResponseFactory
type FauxContentBlock = TextContent | ThinkingContent | ToolCall


def faux_text(text: str, *, text_signature: str | None = None) -> TextContent:
    return TextContent(text=text, text_signature=text_signature)


def faux_thinking(
    thinking: str,
    *,
    thinking_signature: str | None = None,
    redacted: bool = False,
) -> ThinkingContent:
    return ThinkingContent(
        thinking=thinking,
        thinking_signature=thinking_signature,
        redacted=redacted,
    )


def faux_tool_call(
    name: str,
    arguments: JSONObject,
    *,
    tool_call_id: str | None = None,
    thought_signature: str | None = None,
) -> ToolCall:
    return ToolCall(
        id=tool_call_id or f"tool_{uuid.uuid4().hex[:8]}",
        name=name,
        arguments=deepcopy(arguments),
        thought_signature=thought_signature,
    )


def faux_assistant_message(
    content: str | FauxContentBlock | list[FauxContentBlock],
    *,
    stop_reason: StopReason = "stop",
    response_id: str | None = None,
    usage: Usage | None = None,
    model: str = DEFAULT_MODEL_ID,
    provider: str = DEFAULT_PROVIDER,
    api: str = DEFAULT_API,
    error_message: str | None = None,
    timestamp: int | None = None,
) -> AssistantMessage:
    normalized_content = _normalize_faux_content(content)
    return AssistantMessage(
        content=deepcopy(normalized_content),
        api=api,
        provider=provider,
        model=model,
        response_id=response_id,
        usage=deepcopy(usage) if usage is not None else Usage(),
        stop_reason=stop_reason,
        error_message=error_message,
        timestamp=timestamp or _timestamp_ms(),
    )


@dataclass(slots=True)
class FauxProviderState:
    call_count: int = 0


@dataclass(slots=True)
class FauxProviderRegistration:
    api: str
    provider: str
    models: list[Model]
    tokens_per_second: float | None = None
    min_token_size: int = DEFAULT_MIN_TOKEN_SIZE
    max_token_size: int = DEFAULT_MAX_TOKEN_SIZE
    state: FauxProviderState = field(default_factory=FauxProviderState)
    _prompt_cache: dict[str, str] = field(default_factory=dict)
    _responses: deque[FauxResponseStep] = field(default_factory=deque)

    def unregister(self) -> None:
        unregister_api_provider(self.api)
        unregister_provider_models(self.provider)

    def set_responses(self, responses: list[FauxResponseStep]) -> None:
        self._responses = deque(responses)

    def append_responses(self, responses: list[FauxResponseStep]) -> None:
        self._responses.extend(responses)

    def get_pending_response_count(self) -> int:
        return len(self._responses)

    def get_model(self, model_id: str | None = None) -> Model:
        if model_id is None:
            return self.models[0]
        for model in self.models:
            if model.id == model_id:
                return model
        raise LookupError(f"Unknown faux model: {model_id}")


def register_faux_provider(
    *,
    api: str | None = None,
    provider: str | None = None,
    tokens_per_second: float | None = None,
    token_size: dict[str, int] | None = None,
    models: list[dict[str, object]] | None = None,
) -> FauxProviderRegistration:
    provider_api = api or f"{DEFAULT_API}-{uuid.uuid4().hex[:8]}"
    provider_name = provider or f"{DEFAULT_PROVIDER}-{uuid.uuid4().hex[:8]}"
    min_token_size = max(
        1,
        min(
            (token_size or {}).get("min", DEFAULT_MIN_TOKEN_SIZE),
            (token_size or {}).get("max", DEFAULT_MAX_TOKEN_SIZE),
        ),
    )
    max_token_size = max(min_token_size, (token_size or {}).get("max", DEFAULT_MAX_TOKEN_SIZE))
    model_definitions = models or [
        {
            "id": DEFAULT_MODEL_ID,
            "name": DEFAULT_MODEL_NAME,
            "reasoning": False,
            "input": ["text", "image"],
            "context_window": 128_000,
            "max_tokens": 16_384,
        }
    ]
    registered_models = [
        Model(
            id=cast(str, model_definition.get("id") or DEFAULT_MODEL_ID),
            name=cast(
                str,
                model_definition.get("name") or model_definition.get("id") or DEFAULT_MODEL_NAME,
            ),
            api=provider_api,
            provider=provider_name,
            base_url=DEFAULT_BASE_URL,
            reasoning=bool(model_definition.get("reasoning", False)),
            input=_coerce_model_input(model_definition.get("input")),
            context_window=_get_int(model_definition.get("context_window"), 128_000),
            max_tokens=_get_int(model_definition.get("max_tokens"), 16_384),
        )
        for model_definition in model_definitions
    ]
    registration = FauxProviderRegistration(
        api=provider_api,
        provider=provider_name,
        models=registered_models,
        tokens_per_second=tokens_per_second,
        min_token_size=min_token_size,
        max_token_size=max_token_size,
    )

    register_models(*registered_models)
    register_api_provider(
        ApiProvider(
            api=provider_api,
            stream=lambda model, context, options=None: _stream_faux(
                registration,
                model,
                context,
                options,
            ),
        )
    )
    return registration


def _stream_faux(
    registration: FauxProviderRegistration,
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> AssistantMessageEventStream:
    stream = create_assistant_message_event_stream()
    registration.state.call_count += 1
    step = registration._responses.popleft() if registration._responses else None

    async def drive() -> None:
        try:
            if step is None:
                message = create_error_message(
                    RuntimeError("No more faux responses queued"),
                    api=registration.api,
                    provider=registration.provider,
                    model=model.id,
                )
                message = with_usage_estimate(message, context, options, registration._prompt_cache)
                stream.push(ErrorEvent(reason="error", error=message))
                stream.end(message)
                return

            resolved = step(context, options, registration.state, model) if callable(step) else step
            message = await maybe_await(resolved)
            message = clone_message(message, registration.api, registration.provider, model.id)
            message = with_usage_estimate(message, context, options, registration._prompt_cache)
            await stream_with_deltas(
                stream,
                message,
                registration.min_token_size,
                registration.max_token_size,
                registration.tokens_per_second,
                options.signal if options else None,
            )
        except Exception as exc:
            message = create_error_message(
                exc,
                api=registration.api,
                provider=registration.provider,
                model=model.id,
            )
            stream.push(ErrorEvent(reason="error", error=message))
            stream.end(message)

    start_background_task(drive())
    return stream


def with_usage_estimate(
    message: AssistantMessage,
    context: Context,
    options: StreamOptions | None,
    prompt_cache: dict[str, str],
) -> AssistantMessage:
    prompt_text = serialize_context(context)
    prompt_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(assistant_content_to_text(message.content))
    input_tokens = prompt_tokens
    cache_read = 0
    cache_write = 0
    session_id = options.session_id if options else None
    cache_retention = options.cache_retention if options else None

    if session_id and cache_retention != "none":
        previous_prompt = prompt_cache.get(session_id)
        if previous_prompt is None:
            cache_write = prompt_tokens
        else:
            cached_chars = common_prefix_length(previous_prompt, prompt_text)
            cache_read = estimate_tokens(previous_prompt[:cached_chars])
            cache_write = estimate_tokens(prompt_text[cached_chars:])
            input_tokens = max(0, prompt_tokens - cache_read)
        prompt_cache[session_id] = prompt_text

    message.usage = Usage(
        input=input_tokens,
        output=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        total_tokens=input_tokens + output_tokens + cache_read + cache_write,
    )
    return message


async def stream_with_deltas(
    stream: AssistantMessageEventStream,
    message: AssistantMessage,
    min_token_size: int,
    max_token_size: int,
    tokens_per_second: float | None,
    signal: object | None,
) -> None:
    partial = AssistantMessage(
        content=[],
        api=message.api,
        provider=message.provider,
        model=message.model,
        response_id=message.response_id,
        usage=deepcopy(message.usage),
        stop_reason=message.stop_reason,
        error_message=message.error_message,
        timestamp=message.timestamp,
    )

    if is_signal_aborted(signal):
        aborted = create_aborted_message(partial)
        stream.push(ErrorEvent(reason="aborted", error=aborted))
        stream.end(aborted)
        return

    stream.push(StartEvent(partial=partial))
    for index, block in enumerate(message.content):
        if is_signal_aborted(signal):
            aborted = create_aborted_message(partial)
            stream.push(ErrorEvent(reason="aborted", error=aborted))
            stream.end(aborted)
            return
        if isinstance(block, ThinkingContent):
            partial.content.append(
                ThinkingContent(
                    thinking="",
                    thinking_signature=block.thinking_signature,
                    redacted=block.redacted,
                )
            )
            stream.push(ThinkingStartEvent(content_index=index, partial=partial))
            try:
                accumulated = ""
                for chunk in split_string_by_token_size(
                    block.thinking,
                    min_token_size,
                    max_token_size,
                ):
                    await schedule_chunk(chunk, tokens_per_second, signal)
                    accumulated += chunk
                    cast(ThinkingContent, partial.content[index]).thinking = accumulated
                    stream.push(
                        ThinkingDeltaEvent(content_index=index, delta=chunk, partial=partial)
                    )
            except RequestAbortedError:
                aborted = create_aborted_message(partial)
                stream.push(ErrorEvent(reason="aborted", error=aborted))
                stream.end(aborted)
                return
            stream.push(
                ThinkingEndEvent(content_index=index, content=block.thinking, partial=partial)
            )
            continue

        if isinstance(block, TextContent):
            partial.content.append(TextContent(text="", text_signature=block.text_signature))
            stream.push(TextStartEvent(content_index=index, partial=partial))
            try:
                accumulated = ""
                for chunk in split_string_by_token_size(block.text, min_token_size, max_token_size):
                    await schedule_chunk(chunk, tokens_per_second, signal)
                    accumulated += chunk
                    cast(TextContent, partial.content[index]).text = accumulated
                    stream.push(TextDeltaEvent(content_index=index, delta=chunk, partial=partial))
            except RequestAbortedError:
                aborted = create_aborted_message(partial)
                stream.push(ErrorEvent(reason="aborted", error=aborted))
                stream.end(aborted)
                return
            stream.push(TextEndEvent(content_index=index, content=block.text, partial=partial))
            continue

        partial.content.append(ToolCall(id=block.id, name=block.name, arguments={}))
        stream.push(ToolCallStartEvent(content_index=index, partial=partial))
        accumulated_json = ""
        try:
            for chunk in split_string_by_token_size(
                json.dumps(block.arguments, separators=(",", ":")),
                min_token_size,
                max_token_size,
            ):
                await schedule_chunk(chunk, tokens_per_second, signal)
                accumulated_json += chunk
                cast(ToolCall, partial.content[index]).arguments = parse_streaming_json(
                    accumulated_json
                )
                stream.push(ToolCallDeltaEvent(content_index=index, delta=chunk, partial=partial))
        except RequestAbortedError:
            aborted = create_aborted_message(partial)
            stream.push(ErrorEvent(reason="aborted", error=aborted))
            stream.end(aborted)
            return
        cast(ToolCall, partial.content[index]).arguments = deepcopy(block.arguments)
        stream.push(ToolCallEndEvent(content_index=index, tool_call=block, partial=partial))

    if message.stop_reason in {"error", "aborted"}:
        stream.push(
            ErrorEvent(
                reason=cast(Literal["aborted", "error"], message.stop_reason),
                error=message,
            )
        )
        stream.end(message)
        return

    stream.push(
        DoneEvent(
            reason=cast(Literal["stop", "length", "toolUse"], message.stop_reason),
            message=message,
        )
    )
    stream.end(message)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def serialize_context(context: Context) -> str:
    parts: list[str] = []
    if context.system_prompt:
        parts.append(f"system:{context.system_prompt}")
    for message in context.messages:
        parts.append(f"{message.role}:{message_to_text(message)}")
    if context.tools:
        tools_payload = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in context.tools
        ]
        parts.append(f"tools:{json.dumps(tools_payload, separators=(',', ':'))}")
    return "\n\n".join(parts)


def message_to_text(message: Message) -> str:
    if message.role == "user":
        return content_to_text(message.content)
    if message.role == "assistant":
        return assistant_content_to_text(message.content)
    return tool_result_to_text(message)


def content_to_text(content: str | list[TextContent | ImageContent]) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        block.text
        if isinstance(block, TextContent)
        else f"[image:{block.mime_type}:{len(block.data)}]"
        for block in content
    )


def assistant_content_to_text(content: list[TextContent | ThinkingContent | ToolCall]) -> str:
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif isinstance(block, ThinkingContent):
            parts.append(block.thinking)
        else:
            parts.append(f"{block.name}:{json.dumps(block.arguments, separators=(',', ':'))}")
    return "\n".join(parts)


def tool_result_to_text(message: ToolResultMessage) -> str:
    return "\n".join([message.tool_name, *[content_to_text([block]) for block in message.content]])


def common_prefix_length(a: str, b: str) -> int:
    index = 0
    length = min(len(a), len(b))
    while index < length and a[index] == b[index]:
        index += 1
    return index


def split_string_by_token_size(text: str, min_token_size: int, max_token_size: int) -> list[str]:
    chunks: list[str] = []
    index = 0
    while index < len(text):
        token_size = random.randint(min_token_size, max_token_size)
        char_size = max(1, token_size * 4)
        chunks.append(text[index: index + char_size])
        index += char_size
    return chunks or [""]


async def schedule_chunk(
    chunk: str,
    tokens_per_second: float | None,
    signal: object | None,
) -> None:
    raise_if_signal_aborted(signal)
    if not tokens_per_second or tokens_per_second <= 0:
        await asyncio.sleep(0)
        raise_if_signal_aborted(signal)
        return

    delay_seconds = estimate_tokens(chunk) / tokens_per_second
    sleep_task = asyncio.create_task(asyncio.sleep(delay_seconds))
    abort_task = create_abort_task(signal)
    try:
        if abort_task is None:
            await sleep_task
            raise_if_signal_aborted(signal)
            return

        done, _pending = await asyncio.wait(
            {sleep_task, abort_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if abort_task in done:
            sleep_task.cancel()
            await asyncio.gather(sleep_task, return_exceptions=True)
            raise RequestAbortedError("Request was aborted")
        await sleep_task
        raise_if_signal_aborted(signal)
    finally:
        if abort_task is not None:
            abort_task.cancel()
            await asyncio.gather(abort_task, return_exceptions=True)


def clone_message(
    message: AssistantMessage,
    api: str,
    provider: str,
    model_id: str,
) -> AssistantMessage:
    cloned = deepcopy(message)
    cloned.api = api
    cloned.provider = provider
    cloned.model = model_id
    if cloned.timestamp == 0:
        cloned.timestamp = _timestamp_ms()
    if cloned.usage.total_tokens == 0 and cloned.usage.input == 0 and cloned.usage.output == 0:
        cloned.usage = Usage()
    return cloned


def create_error_message(
    error: Exception,
    *,
    api: str,
    provider: str,
    model: str,
) -> AssistantMessage:
    return AssistantMessage(
        api=api,
        provider=provider,
        model=model,
        stop_reason="error",
        error_message=str(error),
        usage=Usage(),
        timestamp=_timestamp_ms(),
    )


def create_aborted_message(partial: AssistantMessage) -> AssistantMessage:
    aborted = deepcopy(partial)
    aborted.stop_reason = "aborted"
    aborted.error_message = "Request was aborted"
    aborted.timestamp = _timestamp_ms()
    return aborted


def _normalize_faux_content(
    content: str | FauxContentBlock | list[FauxContentBlock],
) -> list[FauxContentBlock]:
    if isinstance(content, str):
        return [faux_text(content)]
    if isinstance(content, list):
        return content
    return [content]


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _coerce_model_input(value: object) -> list[Literal["text", "image"]]:
    if not isinstance(value, list):
        return ["text", "image"]
    result: list[Literal["text", "image"]] = []
    for item in value:
        if item == "image":
            result.append("image")
        else:
            result.append("text")
    return result or ["text", "image"]


def _get_int(value: object, default: int) -> int:
    return int(value) if isinstance(value, int | float | str) else default
