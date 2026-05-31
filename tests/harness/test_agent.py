from __future__ import annotations

import asyncio
from typing import cast

import pytest

from epsilon.harness import Agent, AgentInitialState, AgentTool, AgentToolResult
from epsilon.llm import (
    AssistantMessage,
    TextContent,
    ToolResultMessage,
    UserMessage,
)
from epsilon.llm.providers import (
    faux_assistant_message,
    faux_text,
    faux_thinking,
    faux_tool_call,
    register_faux_provider,
)


def _message_text(message) -> str:
    return "\n".join(
        block.text
        for block in message.content
        if isinstance(block, TextContent) or block.type == "text"
    )


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Condition was not met before timeout")
        await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_agent_prompt_updates_state_with_faux_provider() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses([faux_assistant_message("4")])

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model(),
            )
        )

        await agent.prompt("What is 2 + 2?")

        assert agent.state.is_streaming is False
        assert [message.role for message in agent.state.messages] == ["user", "assistant"]
        assert _message_text(agent.state.messages[-1]) == "4"
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_abort_during_streaming_updates_error_state() -> None:
    registration = register_faux_provider(tokens_per_second=20, token_size={"min": 2, "max": 2})
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    "one two three four five six seven eight nine ten eleven twelve "
                    "thirteen fourteen fifteen"
                )
            ]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model(),
            )
        )

        prompt_task = asyncio.create_task(agent.prompt("Count slowly from 1 to 20."))
        await _wait_until(lambda: agent.state.streaming_message is not None)
        await asyncio.sleep(0.03)
        agent.abort()
        await prompt_task

        assert agent.state.is_streaming is False
        assert len(agent.state.messages) >= 2
        last_message = cast(AssistantMessage, agent.state.messages[-1])
        assert last_message.role == "assistant"
        assert last_message.stop_reason == "aborted"
        assert last_message.error_message is not None
        assert agent.state.error_message == last_message.error_message
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_wait_for_idle_awaits_agent_end_subscribers() -> None:
    registration = register_faux_provider(token_size={"min": 1, "max": 1})
    try:
        registration.set_responses([faux_assistant_message("hello")])

        agent = Agent(initial_state=AgentInitialState(model=registration.get_model()))
        barrier = asyncio.Event()
        listener_finished = False

        async def listener(event, _signal) -> None:
            nonlocal listener_finished
            if event.type == "agent_end":
                await barrier.wait()
                listener_finished = True

        agent.subscribe(listener)

        prompt_task = asyncio.create_task(agent.prompt("Hi"))
        await asyncio.sleep(0)
        idle_task = asyncio.create_task(agent.wait_for_idle())
        await asyncio.sleep(0)

        assert agent.state.is_streaming is True
        assert listener_finished is False
        assert idle_task.done() is False

        barrier.set()
        await asyncio.gather(prompt_task, idle_task)

        assert listener_finished is True
        assert agent.state.is_streaming is False
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_subscribers_receive_active_abort_signal() -> None:
    registration = register_faux_provider(tokens_per_second=20, token_size={"min": 1, "max": 1})
    try:
        registration.set_responses([faux_assistant_message("abcdefghijklmnopqrstuvwxyz")])

        agent = Agent(initial_state=AgentInitialState(model=registration.get_model()))
        received_signal = None

        def listener(event, signal) -> None:
            nonlocal received_signal
            if event.type == "agent_start":
                received_signal = signal

        agent.subscribe(listener)

        prompt_task = asyncio.create_task(agent.prompt("hello"))
        await _wait_until(lambda: received_signal is not None)

        assert received_signal is not None
        assert received_signal.aborted is False

        agent.abort()
        await prompt_task

        assert received_signal.aborted is True
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_executes_tools_and_tracks_pending_tool_calls() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses(
            [
                faux_assistant_message(
                    [
                        faux_text("Using the echo tool."),
                        faux_tool_call("echo", {"value": "hello"}, tool_call_id="tool-1"),
                    ],
                    stop_reason="toolUse",
                ),
                faux_assistant_message("done"),
            ]
        )

        async def execute_echo(_tool_call_id: str, params: object, _signal, _on_update):
            assert isinstance(params, dict)
            value = params["value"]
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
        pending_states: list[tuple[str, frozenset[str]]] = []

        agent = Agent(
            initial_state=AgentInitialState(
                model=registration.get_model(),
                tools=[tool],
            )
        )

        def listener(event, _signal) -> None:
            if event.type in {"tool_execution_start", "tool_execution_end"}:
                pending_states.append((event.type, agent.state.pending_tool_calls))

        agent.subscribe(listener)

        await agent.prompt("Echo hello")

        tool_results = [message for message in agent.state.messages if message.role == "toolResult"]
        assert len(tool_results) == 1
        assert _message_text(tool_results[0]) == "echoed: hello"
        assert pending_states == [
            ("tool_execution_start", frozenset({"tool-1"})),
            ("tool_execution_end", frozenset()),
        ]
        assert _message_text(agent.state.messages[-1]) == "done"
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_prompt_raises_while_streaming() -> None:
    registration = register_faux_provider(tokens_per_second=20, token_size={"min": 1, "max": 1})
    try:
        registration.set_responses([faux_assistant_message("abcdefghijklmnopqrstuvwxyz")])

        agent = Agent(initial_state=AgentInitialState(model=registration.get_model()))

        prompt_task = asyncio.create_task(agent.prompt("First message"))
        await _wait_until(lambda: agent.state.is_streaming)

        with pytest.raises(
            RuntimeError,
            match=(
                r"Agent is already processing a prompt. Use steer\(\) or follow_up\(\) "
                r"to queue messages, or wait for completion\."
            ),
        ):
            await agent.prompt("Second message")

        agent.abort()
        await prompt_task
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_raises_while_streaming() -> None:
    registration = register_faux_provider(tokens_per_second=20, token_size={"min": 1, "max": 1})
    try:
        registration.set_responses([faux_assistant_message("abcdefghijklmnopqrstuvwxyz")])

        agent = Agent(initial_state=AgentInitialState(model=registration.get_model()))

        prompt_task = asyncio.create_task(agent.prompt("First message"))
        await _wait_until(lambda: agent.state.is_streaming)

        with pytest.raises(
            RuntimeError,
            match=r"Agent is already processing\. Wait for completion before continuing\.",
        ):
            await agent.continue_()

        agent.abort()
        await prompt_task
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_raises_when_no_messages_exist() -> None:
    registration = register_faux_provider()
    try:
        agent = Agent(initial_state=AgentInitialState(model=registration.get_model()))

        with pytest.raises(RuntimeError, match="No messages to continue from"):
            await agent.continue_()
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_raises_when_last_message_is_assistant() -> None:
    registration = register_faux_provider()
    try:
        model = registration.get_model()
        agent = Agent(
            initial_state=AgentInitialState(
                model=model,
                messages=[
                    faux_assistant_message(
                        "Hello",
                        api=registration.api,
                        provider=registration.provider,
                        model=model.id,
                    )
                ],
            )
        )

        with pytest.raises(RuntimeError, match="Cannot continue from message role: assistant"):
            await agent.continue_()
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_from_user_message() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses([faux_assistant_message("HELLO WORLD")])

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant. Follow instructions exactly.",
                model=registration.get_model(),
                messages=[UserMessage(content="Say exactly: HELLO WORLD", timestamp=1)],
            )
        )

        await agent.continue_()

        assert agent.state.is_streaming is False
        assert [message.role for message in agent.state.messages] == ["user", "assistant"]
        assert _message_text(agent.state.messages[-1]).upper() == "HELLO WORLD"
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_from_tool_result_message() -> None:
    registration = register_faux_provider()
    try:
        model = registration.get_model()
        registration.set_responses([faux_assistant_message("The answer is 8.")])

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="State the answer clearly after getting the tool result.",
                model=model,
                messages=[
                    UserMessage(content="What is 5 + 3?", timestamp=1),
                    faux_assistant_message(
                        [
                            faux_text("Let me calculate that."),
                            faux_tool_call(
                                "calculate",
                                {"expression": "5 + 3"},
                                tool_call_id="calc-1",
                            ),
                        ],
                        stop_reason="toolUse",
                        api=registration.api,
                        provider=registration.provider,
                        model=model.id,
                    ),
                    ToolResultMessage(
                        tool_call_id="calc-1",
                        tool_name="calculate",
                        content=[TextContent(text="5 + 3 = 8")],
                        is_error=False,
                        timestamp=2,
                    ),
                ],
            )
        )

        await agent.continue_()

        assert agent.state.is_streaming is False
        assert len(agent.state.messages) >= 4
        assert agent.state.messages[-1].role == "assistant"
        assert "8" in _message_text(agent.state.messages[-1])
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_uses_follow_up_queue_from_assistant_tail() -> None:
    registration = register_faux_provider()
    try:
        model = registration.get_model()
        registration.set_responses([faux_assistant_message("Processed follow-up")])

        agent = Agent(
            initial_state=AgentInitialState(
                model=model,
                messages=[
                    UserMessage(content="Initial", timestamp=1),
                    faux_assistant_message(
                        "Initial response",
                        api=registration.api,
                        provider=registration.provider,
                        model=model.id,
                    ),
                ],
            )
        )
        agent.follow_up(UserMessage(content="Queued follow-up", timestamp=2))

        await agent.continue_()

        roles = [message.role for message in agent.state.messages[-3:]]
        assert roles == ["assistant", "user", "assistant"]
        assert _message_text(agent.state.messages[-1]) == "Processed follow-up"
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_continue_uses_one_at_a_time_steering_from_assistant_tail() -> None:
    registration = register_faux_provider()
    try:
        model = registration.get_model()
        registration.set_responses(
            [
                faux_assistant_message("Processed 1"),
                faux_assistant_message("Processed 2"),
            ]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                model=model,
                messages=[
                    UserMessage(content="Initial", timestamp=1),
                    faux_assistant_message(
                        "Initial response",
                        api=registration.api,
                        provider=registration.provider,
                        model=model.id,
                    ),
                ],
            )
        )
        agent.steer(UserMessage(content="Steering 1", timestamp=2))
        agent.steer(UserMessage(content="Steering 2", timestamp=3))

        await agent.continue_()

        recent_messages = agent.state.messages[-4:]
        assert [message.role for message in recent_messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert _message_text(agent.state.messages[-1]) == "Processed 2"
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_maintains_context_across_multiple_turns() -> None:
    registration = register_faux_provider()
    try:
        registration.set_responses(
            [
                faux_assistant_message("Nice to meet you, Alice."),
                lambda context, _options, _state, _model: faux_assistant_message(
                    "Your name is Alice."
                    if any(
                        message.role == "user"
                        and (
                            message.content == "My name is Alice."
                            or (
                                isinstance(message.content, list)
                                and any(
                                    block.type == "text" and block.text == "My name is Alice."
                                    for block in message.content
                                )
                            )
                        )
                        for message in context.messages
                    )
                    else "I do not know your name."
                ),
            ]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model(),
            )
        )

        await agent.prompt("My name is Alice.")
        await agent.prompt("What is my name?")

        assert len(agent.state.messages) == 4
        assert "alice" in _message_text(agent.state.messages[-1]).lower()
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_preserves_thinking_content_blocks() -> None:
    registration = register_faux_provider(
        models=[{"id": "faux-reasoning", "name": "Faux Reasoning", "reasoning": True}]
    )
    try:
        registration.set_responses(
            [faux_assistant_message([faux_thinking("step by step"), faux_text("4")])]
        )

        agent = Agent(
            initial_state=AgentInitialState(
                system_prompt="You are a helpful assistant.",
                model=registration.get_model("faux-reasoning"),
                thinking_level="low",
            )
        )

        await agent.prompt("What is 2 + 2?")

        assistant_message = cast(AssistantMessage, agent.state.messages[1])
        assert assistant_message.role == "assistant"
        assert assistant_message.content == [faux_thinking("step by step"), faux_text("4")]
    finally:
        registration.unregister()


@pytest.mark.asyncio
async def test_agent_forwards_session_id_to_provider_options() -> None:
    registration = register_faux_provider()
    try:
        seen_session_ids: list[str | None] = []

        def record_session_id(_context, options, _state, _model):
            seen_session_ids.append(options.session_id if options is not None else None)
            return faux_assistant_message("ok")

        registration.set_responses([record_session_id, record_session_id])

        agent = Agent(
            initial_state=AgentInitialState(model=registration.get_model()),
            session_id="session-abc",
        )

        await agent.prompt("hello")
        agent.session_id = "session-def"
        await agent.prompt("hello again")

        assert seen_session_ids == ["session-abc", "session-def"]
    finally:
        registration.unregister()
