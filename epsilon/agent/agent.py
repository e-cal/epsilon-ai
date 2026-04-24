from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import cast

from ..llm.runtime import maybe_await
from ..llm.types import (
    AssistantMessage,
    ImageContent,
    Message,
    Model,
    TextContent,
    Transport,
    Usage,
    UserMessage,
)
from .agent_loop import run_agent_loop, run_agent_loop_continue
from .types import (
    AbortSignal,
    AfterToolCallFn,
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentInitialState,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    BeforeToolCallFn,
    ConvertToLlmFn,
    GetApiKeyFn,
    MessageStartEvent,
    MessageUpdateEvent,
    QueueMode,
    ReasoningLevel,
    StreamFn,
    ToolExecutionMode,
    TransformContextFn,
)


def _default_model() -> Model:
    return Model(id="unknown", name="unknown", api="unknown", provider="unknown")


def _default_convert_to_llm(messages: list[AgentMessage]) -> list[Message]:
    filtered = [
        message
        for message in messages
        if getattr(message, "role", None) in {"user", "assistant", "toolResult"}
    ]
    return cast(list[Message], filtered)


class AgentState:
    def __init__(self, initial_state: AgentInitialState | None = None) -> None:
        initial = initial_state or AgentInitialState()
        self.system_prompt = initial.system_prompt
        self.model = deepcopy(initial.model) if initial.model is not None else _default_model()
        self.thinking_level: ReasoningLevel = initial.thinking_level
        self._tools: list[AgentTool] = list(initial.tools)
        self._messages: list[AgentMessage] = list(initial.messages)
        self.is_streaming = False
        self.streaming_message: AgentMessage | None = None
        self.pending_tool_calls: frozenset[str] = frozenset()
        self.error_message: str | None = None

    @property
    def tools(self) -> list[AgentTool]:
        return self._tools

    @tools.setter
    def tools(self, tools: list[AgentTool]) -> None:
        self._tools = list(tools)

    @property
    def messages(self) -> list[AgentMessage]:
        return self._messages

    @messages.setter
    def messages(self, messages: list[AgentMessage]) -> None:
        self._messages = list(messages)


class _PendingMessageQueue:
    def __init__(self, mode: QueueMode) -> None:
        self.mode: QueueMode = mode
        self._messages: list[AgentMessage] = []

    def enqueue(self, message: AgentMessage) -> None:
        self._messages.append(message)

    def has_items(self) -> bool:
        return bool(self._messages)

    def drain(self) -> list[AgentMessage]:
        if self.mode == "all":
            drained = list(self._messages)
            self._messages.clear()
            return drained
        if not self._messages:
            return []
        return [self._messages.pop(0)]

    def clear(self) -> None:
        self._messages.clear()


class _ActiveRun:
    def __init__(self) -> None:
        self.signal = AbortSignal()
        self.idle_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()


class Agent:
    def __init__(
        self,
        *,
        initial_state: AgentInitialState | None = None,
        convert_to_llm: ConvertToLlmFn | None = None,
        transform_context: TransformContextFn | None = None,
        stream_fn: StreamFn | None = None,
        get_api_key: GetApiKeyFn | None = None,
        on_payload: (
            Callable[[object, Model], object | Awaitable[object | None] | None] | None
        ) = None,
        before_tool_call: BeforeToolCallFn | None = None,
        after_tool_call: AfterToolCallFn | None = None,
        steering_mode: QueueMode = "one-at-a-time",
        follow_up_mode: QueueMode = "one-at-a-time",
        session_id: str | None = None,
        thinking_budgets: dict[ReasoningLevel, int] | None = None,
        transport: Transport = "sse",
        max_retry_delay_ms: int | None = None,
        tool_execution: ToolExecutionMode = "parallel",
    ) -> None:
        self._state = AgentState(initial_state)
        self.convert_to_llm = convert_to_llm or _default_convert_to_llm
        self.transform_context = transform_context
        self.stream_fn = stream_fn
        self.get_api_key = get_api_key
        self.on_payload = on_payload
        self.before_tool_call = before_tool_call
        self.after_tool_call = after_tool_call
        self._listeners: list[Callable[[AgentEvent, AbortSignal], object | Awaitable[object]]] = []
        self._steering_queue = _PendingMessageQueue(steering_mode)
        self._follow_up_queue = _PendingMessageQueue(follow_up_mode)
        self._active_run: _ActiveRun | None = None
        self.session_id = session_id
        self.thinking_budgets = thinking_budgets
        self.transport: Transport = transport
        self.max_retry_delay_ms = max_retry_delay_ms
        self.tool_execution: ToolExecutionMode = tool_execution

    def subscribe(
        self,
        listener: Callable[[AgentEvent, AbortSignal], object | Awaitable[object]],
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def steering_mode(self) -> QueueMode:
        return self._steering_queue.mode

    @steering_mode.setter
    def steering_mode(self, mode: QueueMode) -> None:
        self._steering_queue.mode = mode

    @property
    def follow_up_mode(self) -> QueueMode:
        return self._follow_up_queue.mode

    @follow_up_mode.setter
    def follow_up_mode(self, mode: QueueMode) -> None:
        self._follow_up_queue.mode = mode

    def steer(self, message: AgentMessage) -> None:
        self._steering_queue.enqueue(message)

    def follow_up(self, message: AgentMessage) -> None:
        self._follow_up_queue.enqueue(message)

    def clear_steering_queue(self) -> None:
        self._steering_queue.clear()

    def clear_follow_up_queue(self) -> None:
        self._follow_up_queue.clear()

    def clear_all_queues(self) -> None:
        self.clear_steering_queue()
        self.clear_follow_up_queue()

    def has_queued_messages(self) -> bool:
        return self._steering_queue.has_items() or self._follow_up_queue.has_items()

    @property
    def signal(self) -> AbortSignal | None:
        return self._active_run.signal if self._active_run is not None else None

    def abort(self) -> None:
        if self._active_run is not None:
            self._active_run.signal.abort()

    async def wait_for_idle(self) -> None:
        if self._active_run is None:
            return
        await self._active_run.idle_future

    def reset(self) -> None:
        self._state.messages = []
        self._state.is_streaming = False
        self._state.streaming_message = None
        self._state.pending_tool_calls = frozenset()
        self._state.error_message = None
        self.clear_all_queues()

    async def prompt(
        self,
        input: str | AgentMessage | list[AgentMessage],
        images: list[ImageContent] | None = None,
    ) -> None:
        if self._active_run is not None:
            raise RuntimeError(
                "Agent is already processing a prompt. Use steer() or follow_up() "
                "to queue messages, or wait for completion."
            )
        messages = self._normalize_prompt_input(input, images)
        await self._run_prompt_messages(messages)

    async def continue_(self) -> None:
        if self._active_run is not None:
            raise RuntimeError(
                "Agent is already processing. Wait for completion before continuing."
            )

        last_message = self._state.messages[-1] if self._state.messages else None
        if last_message is None:
            raise RuntimeError("No messages to continue from")

        if getattr(last_message, "role", None) == "assistant":
            queued_steering = self._steering_queue.drain()
            if queued_steering:
                await self._run_prompt_messages(
                    queued_steering,
                    skip_initial_steering_poll=True,
                )
                return

            queued_follow_ups = self._follow_up_queue.drain()
            if queued_follow_ups:
                await self._run_prompt_messages(queued_follow_ups)
                return

            raise RuntimeError("Cannot continue from message role: assistant")

        await self._run_continuation()

    resume = continue_

    def _normalize_prompt_input(
        self,
        input: str | AgentMessage | list[AgentMessage],
        images: list[ImageContent] | None,
    ) -> list[AgentMessage]:
        if isinstance(input, list):
            return list(input)
        if not isinstance(input, str):
            return [input]

        content: list[TextContent | ImageContent] = [TextContent(text=input)]
        if images:
            content.extend(images)
        return [UserMessage(content=content, timestamp=_timestamp_ms())]

    async def _run_prompt_messages(
        self,
        messages: list[AgentMessage],
        *,
        skip_initial_steering_poll: bool = False,
    ) -> None:
        async def executor(signal: AbortSignal) -> None:
            await run_agent_loop(
                messages,
                self._create_context_snapshot(),
                self._create_loop_config(
                    skip_initial_steering_poll=skip_initial_steering_poll,
                ),
                self._process_event,
                signal,
                self.stream_fn,
            )

        await self._run_with_lifecycle(executor)

    async def _run_continuation(self) -> None:
        async def executor(signal: AbortSignal) -> None:
            await run_agent_loop_continue(
                self._create_context_snapshot(),
                self._create_loop_config(),
                self._process_event,
                signal,
                self.stream_fn,
            )

        await self._run_with_lifecycle(executor)

    def _create_context_snapshot(self) -> AgentContext:
        return AgentContext(
            system_prompt=self._state.system_prompt,
            messages=list(self._state.messages),
            tools=list(self._state.tools),
        )

    def _create_loop_config(
        self,
        *,
        skip_initial_steering_poll: bool = False,
    ) -> AgentLoopConfig:
        should_skip_initial_steering_poll = skip_initial_steering_poll

        async def get_steering_messages() -> list[AgentMessage]:
            nonlocal should_skip_initial_steering_poll
            if should_skip_initial_steering_poll:
                should_skip_initial_steering_poll = False
                return []
            return self._steering_queue.drain()

        return AgentLoopConfig(
            model=self._state.model,
            convert_to_llm=self.convert_to_llm,
            transform_context=self.transform_context,
            get_api_key=self.get_api_key,
            get_steering_messages=get_steering_messages,
            get_follow_up_messages=self._follow_up_queue.drain,
            tool_execution=self.tool_execution,
            before_tool_call=self.before_tool_call,
            after_tool_call=self.after_tool_call,
            reasoning=self._state.thinking_level,
            session_id=self.session_id,
            on_payload=self.on_payload,
            transport=self.transport,
            thinking_budgets=self.thinking_budgets,
            max_retry_delay_ms=self.max_retry_delay_ms,
        )

    async def _run_with_lifecycle(
        self,
        executor: Callable[[AbortSignal], Awaitable[None]],
    ) -> None:
        if self._active_run is not None:
            raise RuntimeError("Agent is already processing.")

        active_run = _ActiveRun()
        self._active_run = active_run
        self._state.is_streaming = True
        self._state.streaming_message = None
        self._state.error_message = None

        try:
            await executor(active_run.signal)
        except Exception as exc:
            await self._handle_run_failure(exc, active_run.signal.aborted)
        finally:
            self._finish_run(active_run)

    async def _handle_run_failure(self, error: Exception, aborted: bool) -> None:
        failure_message = AssistantMessage(
            content=[TextContent(text="")],
            api=self._state.model.api,
            provider=self._state.model.provider,
            model=self._state.model.id,
            usage=Usage(),
            stop_reason="aborted" if aborted else "error",
            error_message=str(error),
            timestamp=_timestamp_ms(),
        )
        self._state.messages.append(failure_message)
        self._state.error_message = failure_message.error_message
        await self._process_event(AgentEndEvent(messages=[failure_message]))

    def _finish_run(self, active_run: _ActiveRun) -> None:
        self._state.is_streaming = False
        self._state.streaming_message = None
        self._state.pending_tool_calls = frozenset()
        if not active_run.idle_future.done():
            active_run.idle_future.set_result(None)
        if self._active_run is active_run:
            self._active_run = None

    async def _process_event(self, event: AgentEvent) -> None:
        if event.type in {"message_start", "message_update"}:
            message_event = cast(MessageStartEvent | MessageUpdateEvent, event)
            self._state.streaming_message = message_event.message
        elif event.type == "message_end":
            self._state.streaming_message = None
            self._state.messages.append(event.message)
        elif event.type == "tool_execution_start":
            pending = set(self._state.pending_tool_calls)
            pending.add(event.tool_call_id)
            self._state.pending_tool_calls = frozenset(pending)
        elif event.type == "tool_execution_end":
            pending = set(self._state.pending_tool_calls)
            pending.discard(event.tool_call_id)
            self._state.pending_tool_calls = frozenset(pending)
        elif event.type == "turn_end":
            if (
                isinstance(event.message, AssistantMessage)
                and event.message.error_message is not None
            ):
                self._state.error_message = event.message.error_message
        elif event.type == "agent_end":
            self._state.streaming_message = None

        if self._active_run is None:
            raise RuntimeError("Agent listener invoked outside active run")

        signal = self._active_run.signal
        for listener in list(self._listeners):
            await maybe_await(listener(event, signal))


def _timestamp_ms() -> int:
    return int(time.time() * 1000)
