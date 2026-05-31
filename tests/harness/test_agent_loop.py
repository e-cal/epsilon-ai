from __future__ import annotations

import asyncio
from typing import cast

import pytest

from epsilon.harness import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AgentToolResult,
    agent_loop,
    agent_loop_continue,
)
from epsilon.llm import (
    TextContent,
    ToolResultMessage,
    UserMessage,
)
from epsilon.llm.providers import (
    faux_assistant_message,
    faux_tool_call,
    register_faux_provider,
)


def _identity_convert_to_llm(messages):
    return [
        message
        for message in messages
        if getattr(message, "role", None) in {"user", "assistant", "toolResult"}
    ]


@pytest.mark.asyncio
async def test_agent_loop_applies_transform_context_before_convert_to_llm() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses([faux_assistant_message("Response")])

        transformed_messages = []
        converted_messages = []

        def transform_context(messages, _signal):
            transformed_messages.extend(messages[-2:])
            return list(messages[-2:])

        def convert_to_llm(messages):
            converted_messages.extend(messages)
            return _identity_convert_to_llm(messages)

        stream = agent_loop(
            [UserMessage(content="new message", timestamp=5)],
            AgentContext(
                system_prompt="You are helpful.",
                messages=[
                    UserMessage(content="old message 1", timestamp=1),
                    faux_assistant_message("old response 1", timestamp=2),
                    UserMessage(content="old message 2", timestamp=3),
                    faux_assistant_message("old response 2", timestamp=4),
                ],
                tools=[],
            ),
            AgentLoopConfig(
                model=registration.get_model(),
                transform_context=transform_context,
                convert_to_llm=convert_to_llm,
            ),
        )

        async for _event in stream:
            pass

        assert len(transformed_messages) == 2
        assert len(converted_messages) == 2
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_executes_mutated_before_tool_call_args_without_revalidation() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    [faux_tool_call("echo", {"value": "hello"}, tool_call_id="tool-1")],
                    stop_reason="toolUse",
                ),
                faux_assistant_message("done"),
            ]
        )

        executed: list[object] = []

        async def execute_echo(_tool_call_id: str, params: object, _signal, _on_update):
            assert isinstance(params, dict)
            executed.append(params["value"])
            return AgentToolResult(content=[TextContent(text="ok")], details={})

        tool = AgentTool(
            name="echo",
            label="Echo",
            description="Echo a string.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            execute=execute_echo,
        )

        async def before_tool_call(context, _signal):
            assert isinstance(context.args, dict)
            context.args["value"] = 123
            return None

        stream = agent_loop(
            [UserMessage(content="hello", timestamp=1)],
            AgentContext(system_prompt="", messages=[], tools=[tool]),
            AgentLoopConfig(
                model=registration.get_model(),
                convert_to_llm=_identity_convert_to_llm,
                before_tool_call=before_tool_call,
            ),
        )

        async for _event in stream:
            pass

        assert executed == [123]
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_prepares_tool_arguments_for_validation() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    [
                        faux_tool_call(
                            "edit",
                            {"oldText": "before", "newText": "after"},
                            tool_call_id="tool-1",
                        )
                    ],
                    stop_reason="toolUse",
                ),
                faux_assistant_message("done"),
            ]
        )

        executed: list[list[dict[str, str]]] = []

        async def execute_edit(_tool_call_id: str, params: object, _signal, _on_update):
            assert isinstance(params, dict)
            edits = cast(list[dict[str, str]], params["edits"])
            executed.append(edits)
            return AgentToolResult(
                content=[TextContent(text=f"edited {len(edits)}")],
                details={"count": len(edits)},
            )

        tool = AgentTool(
            name="edit",
            label="Edit",
            description="Edit tool.",
            parameters={
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "oldText": {"type": "string"},
                                "newText": {"type": "string"},
                            },
                            "required": ["oldText", "newText"],
                        },
                    }
                },
                "required": ["edits"],
            },
            prepare_arguments=lambda args: {
                "edits": [
                    {
                        "oldText": cast(dict[str, str], args)["oldText"],
                        "newText": cast(dict[str, str], args)["newText"],
                    }
                ]
            }
            if isinstance(args, dict)
            and isinstance(args.get("oldText"), str)
            and isinstance(args.get("newText"), str)
            else args,
            execute=execute_edit,
        )

        stream = agent_loop(
            [UserMessage(content="edit something", timestamp=1)],
            AgentContext(system_prompt="", messages=[], tools=[tool]),
            AgentLoopConfig(
                model=registration.get_model(),
                convert_to_llm=_identity_convert_to_llm,
            ),
        )

        async for _event in stream:
            pass

        assert executed == [[{"oldText": "before", "newText": "after"}]]
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_executes_tools_in_parallel_but_emits_tool_results_in_source_order() -> (
    None
):
    registration = register_faux_provider()
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    [
                        faux_tool_call("echo", {"value": "first"}, tool_call_id="tool-1"),
                        faux_tool_call("echo", {"value": "second"}, tool_call_id="tool-2"),
                    ],
                    stop_reason="toolUse",
                ),
                faux_assistant_message("done"),
            ]
        )

        first_released = asyncio.Event()
        first_finished = False
        parallel_observed = False

        async def execute_echo(_tool_call_id: str, params: object, _signal, _on_update):
            nonlocal first_finished, parallel_observed
            assert isinstance(params, dict)
            value = params["value"]
            if value == "first":
                await first_released.wait()
                first_finished = True
            if value == "second" and not first_finished:
                parallel_observed = True
            return AgentToolResult(
                content=[TextContent(text=f"echoed: {value}")],
                details={"value": value},
            )

        tool = AgentTool(
            name="echo",
            label="Echo",
            description="Echo a string.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            execute=execute_echo,
        )

        asyncio.get_running_loop().call_later(0.02, first_released.set)
        events = [
            event
            async for event in agent_loop(
                [UserMessage(content="run", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[tool]),
                AgentLoopConfig(
                    model=registration.get_model(),
                    convert_to_llm=_identity_convert_to_llm,
                    tool_execution="parallel",
                ),
            )
        ]

        tool_result_ids = [
            cast(ToolResultMessage, event.message).tool_call_id
            for event in events
            if event.type == "message_end" and event.message.role == "toolResult"
        ]

        assert parallel_observed is True
        assert tool_result_ids == ["tool-1", "tool-2"]
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_injects_queued_messages_after_all_tool_calls_complete() -> None:
    registration = register_faux_provider()
    try:
        executed: list[str] = []
        queued_delivered = False
        saw_interrupt_in_context = False
        queued_user_message = UserMessage(content="interrupt", timestamp=2)

        async def execute_echo(_tool_call_id: str, params: object, _signal, _on_update):
            assert isinstance(params, dict)
            value = cast(str, params["value"])
            executed.append(value)
            return AgentToolResult(
                content=[TextContent(text=f"ok:{value}")],
                details={"value": value},
            )

        tool = AgentTool(
            name="echo",
            label="Echo",
            description="Echo a string.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            execute=execute_echo,
        )

        async def get_steering_messages() -> list[AgentMessage]:
            nonlocal queued_delivered
            if len(executed) >= 1 and not queued_delivered:
                queued_delivered = True
                return [cast(AgentMessage, queued_user_message)]
            return []

        def second_response(context, _options, _state, _model):
            nonlocal saw_interrupt_in_context
            saw_interrupt_in_context = any(
                message.role == "user" and message.content == "interrupt"
                for message in context.messages
            )
            return faux_assistant_message("done")

        registration.set_responses(
            [
                faux_assistant_message(
                    [
                        faux_tool_call("echo", {"value": "first"}, tool_call_id="tool-1"),
                        faux_tool_call("echo", {"value": "second"}, tool_call_id="tool-2"),
                    ],
                    stop_reason="toolUse",
                ),
                second_response,
            ]
        )

        events = [
            event
            async for event in agent_loop(
                [UserMessage(content="start", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[tool]),
                AgentLoopConfig(
                    model=registration.get_model(),
                    convert_to_llm=_identity_convert_to_llm,
                    tool_execution="sequential",
                    get_steering_messages=get_steering_messages,
                ),
            )
        ]

        tool_ends = [event for event in events if event.type == "tool_execution_end"]
        event_sequence = []
        for event in events:
            if event.type != "message_start":
                continue
            if event.message.role == "toolResult":
                event_sequence.append(
                    f"tool:{cast(ToolResultMessage, event.message).tool_call_id}"
                )
            elif (
                event.message.role == "user"
                and cast(UserMessage, event.message).content == "interrupt"
            ):
                event_sequence.append("interrupt")

        assert executed == ["first", "second"]
        assert len(tool_ends) == 2
        assert tool_ends[0].is_error is False
        assert tool_ends[1].is_error is False
        assert "interrupt" in event_sequence
        assert event_sequence.index("tool:tool-1") < event_sequence.index("interrupt")
        assert event_sequence.index("tool:tool-2") < event_sequence.index("interrupt")
        assert saw_interrupt_in_context is True
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_continue_raises_when_context_has_no_messages() -> None:
    registration = register_faux_provider()
    try:
        with pytest.raises(ValueError, match="Cannot continue: no messages in context"):
            agent_loop_continue(
                AgentContext(system_prompt="You are helpful.", messages=[], tools=[]),
                AgentLoopConfig(
                    model=registration.get_model(),
                    convert_to_llm=_identity_convert_to_llm,
                ),
            )
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_continue_returns_only_new_messages_without_user_message_events() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses([faux_assistant_message("Response")])

        stream = agent_loop_continue(
            AgentContext(
                system_prompt="You are helpful.",
                messages=[UserMessage(content="Hello", timestamp=1)],
                tools=[],
            ),
            AgentLoopConfig(
                model=registration.get_model(),
                convert_to_llm=_identity_convert_to_llm,
            ),
        )

        events = [event async for event in stream]
        messages = await stream.result()
        message_end_events = [event for event in events if event.type == "message_end"]

        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert len(message_end_events) == 1
        assert message_end_events[0].message.role == "assistant"
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_loop_continue_allows_custom_last_message_via_convert_to_llm() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses([faux_assistant_message("Response to custom message")])

        class CustomMessage:
            def __init__(self, text: str, timestamp: int) -> None:
                self.role = "custom"
                self.text = text
                self.timestamp = timestamp

        def convert_custom_messages(messages):
            converted = []
            for message in messages:
                if getattr(message, "role", None) == "assistant":
                    continue
                if getattr(message, "role", None) == "custom":
                    converted.append(
                        UserMessage(
                            content=message.text,
                            timestamp=message.timestamp,
                        )
                    )
                else:
                    converted.append(message)
            return cast(list, converted)

        stream = agent_loop_continue(
            AgentContext(
                system_prompt="You are helpful.",
                messages=[CustomMessage("Hook content", 1)],
                tools=[],
            ),
            AgentLoopConfig(
                model=registration.get_model(),
                convert_to_llm=convert_custom_messages,
            ),
        )

        async for _event in stream:
            pass

        messages = await stream.result()
        assert len(messages) == 1
        assert messages[0].role == "assistant"
    finally:
        registration.unregister()
