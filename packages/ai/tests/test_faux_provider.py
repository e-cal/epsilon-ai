from __future__ import annotations

import asyncio
from typing import cast

import pytest
from e_ai import (
    Context,
    StreamOptions,
    TextContent,
    UserMessage,
    complete,
    faux_assistant_message,
    faux_text,
    faux_thinking,
    faux_tool_call,
    register_faux_provider,
    stream,
)


class AbortSignal:
    def __init__(self) -> None:
        self.aborted = False
        self._event = asyncio.Event()

    def abort(self) -> None:
        self.aborted = True
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


@pytest.mark.asyncio
async def test_faux_provider_streams_chunked_text_thinking_and_tool_calls() -> None:
    registration = register_faux_provider(token_size={"min": 1, "max": 1})
    registration.set_responses(
        [
            faux_assistant_message(
                [
                    faux_thinking("Need to inspect the file first."),
                    faux_text("I will read the file now."),
                    faux_tool_call("read", {"path": "README.md", "mode": "text"}),
                ],
                stop_reason="toolUse",
            )
        ]
    )

    events = [event async for event in stream(registration.get_model(), Context(messages=[]))]

    event_types = [event.type for event in events]
    assert event_types[0] == "start"
    assert event_types[-1] == "done"
    assert "thinking_start" in event_types
    assert "thinking_delta" in event_types
    assert "thinking_end" in event_types
    assert "text_start" in event_types
    assert "text_delta" in event_types
    assert "text_end" in event_types
    assert "toolcall_start" in event_types
    assert "toolcall_delta" in event_types
    assert "toolcall_end" in event_types

    tool_call_deltas = [event.delta for event in events if event.type == "toolcall_delta"]
    assert len(tool_call_deltas) > 1
    assert "".join(tool_call_deltas) == '{"path":"README.md","mode":"text"}'

    registration.unregister()


@pytest.mark.asyncio
async def test_faux_provider_estimates_usage_and_session_cache() -> None:
    registration = register_faux_provider()
    registration.set_responses([faux_assistant_message("first"), faux_assistant_message("second")])
    model = registration.get_model()

    context = Context(
        system_prompt="Be concise.",
        messages=[UserMessage(content="hello", timestamp=1)],
    )

    options = StreamOptions(session_id="s1", cache_retention="short")
    first = await complete(model, context, options)
    assert first.usage.cache_read == 0
    assert first.usage.cache_write > 0

    context.messages.append(first)
    context.messages.append(UserMessage(content="follow up", timestamp=2))

    second = await complete(model, context, options)
    assert second.usage.cache_read > 0
    assert second.usage.total_tokens == (
        second.usage.input
        + second.usage.output
        + second.usage.cache_read
        + second.usage.cache_write
    )

    registration.unregister()


@pytest.mark.asyncio
async def test_faux_provider_supports_async_factories_and_multiple_models() -> None:
    registration = register_faux_provider(
        models=[
            {"id": "faux-fast", "name": "Faux Fast", "reasoning": False},
            {"id": "faux-thinker", "name": "Faux Thinker", "reasoning": True},
        ]
    )
    registration.set_responses(
        [
            lambda context, _options, state, model: faux_assistant_message(
                f"{len(context.messages)}:{state.call_count}:{model.id}:{model.reasoning}"
            ),
            lambda context, _options, state, model: faux_assistant_message(
                f"{len(context.messages)}:{state.call_count}:{model.id}:{model.reasoning}"
            ),
        ]
    )

    fast = await complete(
        registration.get_model("faux-fast"),
        Context(messages=[UserMessage(content="hi", timestamp=1)]),
    )
    thinker = await complete(
        registration.get_model("faux-thinker"),
        Context(messages=[UserMessage(content="hi", timestamp=1)]),
    )

    assert cast(TextContent, fast.content[0]).text == "1:1:faux-fast:False"
    assert cast(TextContent, thinker.content[0]).text == "1:2:faux-thinker:True"

    registration.unregister()


@pytest.mark.asyncio
async def test_faux_provider_aborts_mid_stream() -> None:
    registration = register_faux_provider(tokens_per_second=100, token_size={"min": 1, "max": 1})
    registration.set_responses([faux_assistant_message("abcdefghijklmnopqrstuvwxyz")])
    signal = AbortSignal()

    event_types: list[str] = []
    s = stream(
        registration.get_model(),
        Context(messages=[UserMessage(content="hi", timestamp=1)]),
        StreamOptions(signal=signal),
    )
    async for event in s:
        event_types.append(event.type)
        if event.type == "text_delta":
            signal.abort()

    result = await s.result()
    assert result.stop_reason == "aborted"
    assert "error" in event_types
    assert "text_start" in event_types
    assert "text_end" not in event_types

    registration.unregister()


@pytest.mark.asyncio
async def test_faux_provider_explicit_error_is_terminal_error() -> None:
    registration = register_faux_provider(token_size={"min": 1, "max": 1})
    registration.set_responses(
        [
            faux_assistant_message(
                "partial",
                stop_reason="error",
                error_message="upstream failed",
            )
        ]
    )

    events = [event async for event in stream(registration.get_model(), Context(messages=[]))]
    terminal = events[-1]

    assert terminal.type == "error"
    if terminal.type == "error":
        assert terminal.reason == "error"
        assert terminal.error.error_message == "upstream failed"

    registration.unregister()


@pytest.mark.asyncio
async def test_faux_provider_errors_when_queue_is_empty() -> None:
    registration = register_faux_provider()
    message = await complete(registration.get_model(), Context(messages=[]))

    assert message.stop_reason == "error"
    assert message.error_message == "No more faux responses queued"

    registration.unregister()
