from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Coroutine
from typing import Literal, cast

from ..event_stream import AssistantMessageEventStream
from ..types import (
    AssistantMessage,
    DoneEvent,
    ErrorEvent,
    StartEvent,
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
)

_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def create_empty_assistant_message(*, api: str, provider: str, model: str) -> AssistantMessage:
    return AssistantMessage(api=api, provider=provider, model=model, timestamp=_timestamp_ms())


def start_background_task(coro: Coroutine[object, object, None]) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def emit_message_as_stream(
    stream: AssistantMessageEventStream,
    message: AssistantMessage,
) -> None:
    partial = AssistantMessage(
        api=message.api,
        provider=message.provider,
        model=message.model,
        response_id=message.response_id,
        usage=message.usage,
        stop_reason=message.stop_reason,
        error_message=message.error_message,
        timestamp=message.timestamp,
    )
    stream.push(StartEvent(partial=partial))

    for index, block in enumerate(message.content):
        partial.content.append(block)
        if isinstance(block, TextContent):
            stream.push(TextStartEvent(content_index=index, partial=partial))
            stream.push(TextDeltaEvent(content_index=index, delta=block.text, partial=partial))
            stream.push(TextEndEvent(content_index=index, content=block.text, partial=partial))
        elif isinstance(block, ThinkingContent):
            stream.push(ThinkingStartEvent(content_index=index, partial=partial))
            stream.push(
                ThinkingDeltaEvent(content_index=index, delta=block.thinking, partial=partial)
            )
            stream.push(
                ThinkingEndEvent(content_index=index, content=block.thinking, partial=partial)
            )
        elif isinstance(block, ToolCall):
            delta = json.dumps(block.arguments, separators=(",", ":"), sort_keys=True)
            stream.push(ToolCallStartEvent(content_index=index, partial=partial))
            stream.push(ToolCallDeltaEvent(content_index=index, delta=delta, partial=partial))
            stream.push(ToolCallEndEvent(content_index=index, tool_call=block, partial=partial))

    if message.stop_reason in {"stop", "length", "toolUse"}:
        stream.push(
            DoneEvent(
                reason=cast(Literal["stop", "length", "toolUse"], message.stop_reason),
                message=message,
            )
        )
        stream.end(message)
    else:
        stream.push(
            ErrorEvent(
                reason=cast(Literal["aborted", "error"], message.stop_reason),
                error=message,
            )
        )
        stream.end(message)


def _timestamp_ms() -> int:
    return int(time.time() * 1000)
