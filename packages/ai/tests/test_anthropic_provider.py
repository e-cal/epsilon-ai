from __future__ import annotations

from collections.abc import AsyncIterator
from copy import deepcopy
from typing import cast

import pytest
from e_ai import Context, Tool, UserMessage
from e_ai.event_stream import AssistantMessageEventStream
from e_ai.models import get_model
from e_ai.providers.anthropic import (
    AnthropicOptions,
    build_anthropic_payload,
    process_anthropic_event_stream,
)
from e_ai.providers.shared import create_empty_assistant_message
from e_ai.types import AssistantMessageEvent, ToolCall, ToolCallDeltaEvent


def _capture_stream_events(stream: AssistantMessageEventStream) -> list[AssistantMessageEvent]:
    captured: list[AssistantMessageEvent] = []
    original_push = stream.push

    def push(event: AssistantMessageEvent) -> None:
        captured.append(deepcopy(event))
        original_push(event)

    stream.push = push  # type: ignore[method-assign]
    return captured


async def _aiter(events: list[dict[str, object]]) -> AsyncIterator[dict[str, object]]:
    for event in events:
        yield event


def test_build_anthropic_payload_disables_thinking_and_applies_cache_control() -> None:
    model = get_model("anthropic", "claude-sonnet-4-5")
    payload = build_anthropic_payload(
        model,
        Context(messages=[UserMessage(content="hello", timestamp=1)], system_prompt="Be concise."),
        AnthropicOptions(thinking_enabled=False, cache_retention="long"),
    )

    assert payload["thinking"] == {"type": "disabled"}
    system_blocks = payload["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_build_anthropic_payload_round_trips_claude_code_tool_names_for_oauth() -> None:
    model = get_model("anthropic", "claude-sonnet-4-20250514")
    payload = build_anthropic_payload(
        model,
        Context(
            messages=[UserMessage(content="add a todo", timestamp=1)],
            tools=[
                Tool(
                    name="todowrite",
                    description="Write a todo item",
                    parameters={"type": "object", "properties": {"task": {"type": "string"}}},
                )
            ],
        ),
        AnthropicOptions(),
        is_oauth_token_value=True,
    )

    tools = payload["tools"]
    assert isinstance(tools, list)
    assert tools[0]["name"] == "TodoWrite"
    system_blocks = payload["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["text"] == "You are Claude Code, Anthropic's official CLI for Claude."


@pytest.mark.asyncio
async def test_process_anthropic_event_stream_emits_partial_tool_json_and_restores_oauth_tool_name() -> None:
    model = get_model("anthropic", "claude-sonnet-4-20250514")
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    stream = AssistantMessageEventStream()
    captured = _capture_stream_events(stream)
    tools = [
        Tool(
            name="todowrite",
            description="Write a todo item",
            parameters={"type": "object", "properties": {"task": {"type": "string"}}},
        )
    ]

    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 2,
                    "cache_creation_input_tokens": 1,
                },
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "plan"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "TodoWrite",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"task":"buy'},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": ' milk"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {
                "input_tokens": 11,
                "output_tokens": 5,
                "cache_read_input_tokens": 2,
                "cache_creation_input_tokens": 1,
            },
        },
    ]

    await process_anthropic_event_stream(_aiter(events), output, stream, model, tools, True)

    event_types = [event.type for event in captured]
    assert event_types == [
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_end",
    ]
    first_tool_delta = cast(ToolCallDeltaEvent, captured[4])
    assert cast(ToolCall, first_tool_delta.partial.content[1]).arguments == {"task": "buy"}
    final_tool_call = cast(ToolCall, output.content[1])
    assert final_tool_call.name == "todowrite"
    assert final_tool_call.arguments == {"task": "buy milk"}
    assert output.stop_reason == "toolUse"
    assert output.usage.total_tokens == 19
