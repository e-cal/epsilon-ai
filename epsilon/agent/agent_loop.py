from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from ..llm.event_stream import EventStream
from ..llm.runtime import maybe_await
from ..llm.stream import stream
from ..llm.types import (
    AssistantMessage,
    Context,
    ImageContent,
    StreamOptions,
    TextContent,
    ToolCall,
    ToolResultMessage,
)
from ..llm.types import (
    ReasoningLevel as LlmReasoningLevel,
)
from ..llm.types import (
    resolve_reasoning_level as resolve_llm_reasoning_level,
)
from .types import (
    UNSET,
    AbortSignal,
    AfterToolCallContext,
    AfterToolCallResult,
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentStartEvent,
    AgentTool,
    AgentToolResult,
    BeforeToolCallContext,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ReasoningLevel,
    StreamFn,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
    normalize_reasoning_level,
)
from .validation import validate_tool_arguments

type AgentEventSink = Callable[[AgentEvent], object | Awaitable[object]]


def agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
) -> EventStream[AgentEvent, list[AgentMessage]]:
    stream = create_agent_event_stream()

    async def drive() -> None:
        messages: list[AgentMessage] = []
        try:
            messages = await run_agent_loop(
                prompts,
                context,
                config,
                stream.push,
                signal,
                stream_fn,
            )
        finally:
            stream.end(messages)

    asyncio.get_running_loop().create_task(drive())
    return stream


def agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
) -> EventStream[AgentEvent, list[AgentMessage]]:
    if not context.messages:
        raise ValueError("Cannot continue: no messages in context")
    if _message_role(context.messages[-1]) == "assistant":
        raise ValueError("Cannot continue from message role: assistant")

    stream = create_agent_event_stream()

    async def drive() -> None:
        messages: list[AgentMessage] = []
        try:
            messages = await run_agent_loop_continue(
                context,
                config,
                stream.push,
                signal,
                stream_fn,
            )
        finally:
            stream.end(messages)

    asyncio.get_running_loop().create_task(drive())
    return stream


def create_agent_event_stream() -> EventStream[AgentEvent, list[AgentMessage]]:
    return EventStream(
        is_complete=lambda event: event.type == "agent_end",
        extract_result=lambda event: event.messages if event.type == "agent_end" else [],
    )


async def run_agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    emit: AgentEventSink,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
) -> list[AgentMessage]:
    new_messages = list(prompts)
    current_context = AgentContext(
        system_prompt=context.system_prompt,
        messages=[*context.messages, *prompts],
        tools=context.tools,
    )

    await maybe_await(emit(AgentStartEvent()))
    await maybe_await(emit(TurnStartEvent()))
    for prompt in prompts:
        await maybe_await(emit(MessageStartEvent(message=_clone_message(prompt))))
        await maybe_await(emit(MessageEndEvent(message=_clone_message(prompt))))

    await _run_loop(current_context, new_messages, config, signal, emit, stream_fn)
    return new_messages


async def run_agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    emit: AgentEventSink,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
) -> list[AgentMessage]:
    if not context.messages:
        raise ValueError("Cannot continue: no messages in context")
    if _message_role(context.messages[-1]) == "assistant":
        raise ValueError("Cannot continue from message role: assistant")

    new_messages: list[AgentMessage] = []
    current_context = AgentContext(
        system_prompt=context.system_prompt,
        messages=list(context.messages),
        tools=context.tools,
    )

    await maybe_await(emit(AgentStartEvent()))
    await maybe_await(emit(TurnStartEvent()))
    await _run_loop(current_context, new_messages, config, signal, emit, stream_fn)
    return new_messages


async def _run_loop(
    current_context: AgentContext,
    new_messages: list[AgentMessage],
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
    stream_fn: StreamFn | None,
) -> None:
    first_turn = True
    pending_messages = await _get_pending_messages(config.get_steering_messages)

    while True:
        has_more_tool_calls = True
        while has_more_tool_calls or pending_messages:
            if first_turn:
                first_turn = False
            else:
                await maybe_await(emit(TurnStartEvent()))

            if pending_messages:
                for message in pending_messages:
                    await maybe_await(emit(MessageStartEvent(message=_clone_message(message))))
                    await maybe_await(emit(MessageEndEvent(message=_clone_message(message))))
                    current_context.messages.append(message)
                    new_messages.append(message)
                pending_messages = []

            assistant_message = await _stream_assistant_response(
                current_context,
                config,
                signal,
                emit,
                stream_fn,
            )
            new_messages.append(assistant_message)

            if assistant_message.stop_reason in {"error", "aborted"}:
                await maybe_await(
                    emit(TurnEndEvent(message=_clone_message(assistant_message), tool_results=[]))
                )
                await maybe_await(emit(AgentEndEvent(messages=list(new_messages))))
                return

            tool_calls = [
                block for block in assistant_message.content if isinstance(block, ToolCall)
            ]
            has_more_tool_calls = bool(tool_calls)

            tool_results: list[ToolResultMessage] = []
            if has_more_tool_calls:
                tool_results.extend(
                    await _execute_tool_calls(
                        current_context,
                        assistant_message,
                        tool_calls,
                        config,
                        signal,
                        emit,
                    )
                )
                for result in tool_results:
                    current_context.messages.append(result)
                    new_messages.append(result)

            await maybe_await(
                emit(
                    TurnEndEvent(
                        message=_clone_message(assistant_message),
                        tool_results=[deepcopy(result) for result in tool_results],
                    )
                )
            )
            pending_messages = await _get_pending_messages(config.get_steering_messages)

        follow_up_messages = await _get_pending_messages(config.get_follow_up_messages)
        if follow_up_messages:
            pending_messages = follow_up_messages
            continue
        break

    await maybe_await(emit(AgentEndEvent(messages=list(new_messages))))


async def _stream_assistant_response(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
    stream_fn: StreamFn | None,
) -> AssistantMessage:
    messages = context.messages
    if config.transform_context is not None:
        messages = list(await maybe_await(config.transform_context(messages, signal)))

    llm_messages = list(await maybe_await(config.convert_to_llm(messages)))
    llm_context = Context(
        system_prompt=context.system_prompt,
        messages=llm_messages,
        tools=[tool.to_llm_tool() for tool in context.tools] if context.tools else None,
    )

    resolved_api_key = config.api_key
    if config.get_api_key is not None:
        dynamic_key = await maybe_await(config.get_api_key(config.model.provider))
        resolved_api_key = dynamic_key or resolved_api_key

    stream_options = StreamOptions(
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        signal=signal,
        api_key=resolved_api_key,
        transport=config.transport,
        cache_retention=config.cache_retention,
        session_id=config.session_id,
        on_payload=config.on_payload,
        headers=config.headers,
        max_retry_delay_ms=config.max_retry_delay_ms,
        metadata=config.metadata,
        reasoning=normalize_reasoning_level(config.reasoning),
        thinking_budgets=_normalize_thinking_budgets(config.thinking_budgets),
    )

    response = (stream_fn or stream)(config.model, llm_context, stream_options)

    partial_message: AssistantMessage | None = None
    added_partial = False
    async for event in response:
        if event.type == "done" or event.type == "error":
            final_message = await response.result()
            if added_partial:
                context.messages[-1] = final_message
            else:
                context.messages.append(final_message)
                await maybe_await(emit(MessageStartEvent(message=_clone_message(final_message))))
            await maybe_await(emit(MessageEndEvent(message=_clone_message(final_message))))
            return final_message

        if event.type == "start":
            partial_message = event.partial
            context.messages.append(partial_message)
            added_partial = True
            await maybe_await(emit(MessageStartEvent(message=_clone_message(partial_message))))
            continue

        partial_message = event.partial
        context.messages[-1] = partial_message
        await maybe_await(
            emit(
                MessageUpdateEvent(
                    message=_clone_message(partial_message),
                    assistant_message_event=deepcopy(event),
                )
            )
        )

    final_message = await response.result()
    if added_partial:
        context.messages[-1] = final_message
    else:
        context.messages.append(final_message)
        await maybe_await(emit(MessageStartEvent(message=_clone_message(final_message))))
    await maybe_await(emit(MessageEndEvent(message=_clone_message(final_message))))
    return final_message


async def _execute_tool_calls(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_calls: list[ToolCall],
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> list[ToolResultMessage]:
    if config.tool_execution == "sequential":
        return await _execute_tool_calls_sequential(
            current_context,
            assistant_message,
            tool_calls,
            config,
            signal,
            emit,
        )
    return await _execute_tool_calls_parallel(
        current_context,
        assistant_message,
        tool_calls,
        config,
        signal,
        emit,
    )


async def _execute_tool_calls_sequential(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_calls: list[ToolCall],
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> list[ToolResultMessage]:
    results: list[ToolResultMessage] = []
    for tool_call in tool_calls:
        await maybe_await(
            emit(
                ToolExecutionStartEvent(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    args=deepcopy(tool_call.arguments),
                )
            )
        )
        preparation = await _prepare_tool_call(
            current_context,
            assistant_message,
            tool_call,
            config,
            signal,
        )
        if isinstance(preparation, _ImmediateToolCallOutcome):
            results.append(
                await _emit_tool_call_outcome(
                    tool_call,
                    preparation.result,
                    preparation.is_error,
                    emit,
                )
            )
            continue

        executed = await _execute_prepared_tool_call(preparation, signal, emit)
        results.append(
            await _finalize_executed_tool_call(
                current_context,
                assistant_message,
                preparation,
                executed,
                config,
                signal,
                emit,
            )
        )
    return results


async def _execute_tool_calls_parallel(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_calls: list[ToolCall],
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> list[ToolResultMessage]:
    results: list[ToolResultMessage] = []
    runnable_calls: list[_PreparedToolCall] = []

    for tool_call in tool_calls:
        await maybe_await(
            emit(
                ToolExecutionStartEvent(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    args=deepcopy(tool_call.arguments),
                )
            )
        )
        preparation = await _prepare_tool_call(
            current_context,
            assistant_message,
            tool_call,
            config,
            signal,
        )
        if isinstance(preparation, _ImmediateToolCallOutcome):
            results.append(
                await _emit_tool_call_outcome(
                    tool_call,
                    preparation.result,
                    preparation.is_error,
                    emit,
                )
            )
            continue
        runnable_calls.append(preparation)

    running_calls = [
        (
            prepared,
            asyncio.create_task(_execute_prepared_tool_call(prepared, signal, emit)),
        )
        for prepared in runnable_calls
    ]

    for prepared, task in running_calls:
        executed = await task
        results.append(
            await _finalize_executed_tool_call(
                current_context,
                assistant_message,
                prepared,
                executed,
                config,
                signal,
                emit,
            )
        )
    return results


@dataclass(slots=True)
class _PreparedToolCall:
    tool_call: ToolCall
    tool: AgentTool
    args: object


@dataclass(slots=True)
class _ImmediateToolCallOutcome:
    result: AgentToolResult
    is_error: bool


@dataclass(slots=True)
class _ExecutedToolCallOutcome:
    result: AgentToolResult
    is_error: bool


def _prepare_tool_call_arguments(tool: AgentTool, tool_call: ToolCall) -> ToolCall:
    if tool.prepare_arguments is None:
        return tool_call
    prepared_arguments = tool.prepare_arguments(tool_call.arguments)
    if prepared_arguments is tool_call.arguments:
        return tool_call
    return ToolCall(
        id=tool_call.id,
        name=tool_call.name,
        arguments=prepared_arguments,  # type: ignore[arg-type]
        thought_signature=tool_call.thought_signature,
    )


async def _prepare_tool_call(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_call: ToolCall,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
) -> _PreparedToolCall | _ImmediateToolCallOutcome:
    tool = next(
        (
            candidate
            for candidate in current_context.tools or []
            if candidate.name == tool_call.name
        ),
        None,
    )
    if tool is None:
        return _ImmediateToolCallOutcome(
            result=_create_error_tool_result(f"Tool {tool_call.name} not found"),
            is_error=True,
        )

    try:
        prepared_tool_call = _prepare_tool_call_arguments(tool, tool_call)
        validated_args = validate_tool_arguments(tool, prepared_tool_call)
        if config.before_tool_call is not None:
            before_result = await maybe_await(
                config.before_tool_call(
                    BeforeToolCallContext(
                        assistant_message=assistant_message,
                        tool_call=tool_call,
                        args=validated_args,
                        context=current_context,
                    ),
                    signal,
                )
            )
            if before_result is not None and before_result.block:
                return _ImmediateToolCallOutcome(
                    result=_create_error_tool_result(
                        before_result.reason or "Tool execution was blocked"
                    ),
                    is_error=True,
                )
        return _PreparedToolCall(tool_call=tool_call, tool=tool, args=validated_args)
    except Exception as exc:
        return _ImmediateToolCallOutcome(
            result=_create_error_tool_result(str(exc)),
            is_error=True,
        )


async def _execute_prepared_tool_call(
    prepared: _PreparedToolCall,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> _ExecutedToolCallOutcome:
    update_tasks: list[asyncio.Task[None]] = []

    def on_update(partial_result: AgentToolResult) -> None:
        async def emit_update() -> None:
            await maybe_await(
                emit(
                    ToolExecutionUpdateEvent(
                        tool_call_id=prepared.tool_call.id,
                        tool_name=prepared.tool_call.name,
                        args=deepcopy(prepared.tool_call.arguments),
                        partial_result=deepcopy(partial_result),
                    )
                )
            )

        update_tasks.append(asyncio.create_task(emit_update()))

    try:
        result = await prepared.tool.execute(
            prepared.tool_call.id,
            prepared.args,
            signal,
            on_update,
        )
        if update_tasks:
            await asyncio.gather(*update_tasks)
        return _ExecutedToolCallOutcome(result=result, is_error=False)
    except Exception as exc:
        if update_tasks:
            await asyncio.gather(*update_tasks)
        return _ExecutedToolCallOutcome(
            result=_create_error_tool_result(str(exc)),
            is_error=True,
        )


async def _finalize_executed_tool_call(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    prepared: _PreparedToolCall,
    executed: _ExecutedToolCallOutcome,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> ToolResultMessage:
    result = executed.result
    is_error = executed.is_error

    if config.after_tool_call is not None:
        try:
            after_result = await maybe_await(
                config.after_tool_call(
                    AfterToolCallContext(
                        assistant_message=assistant_message,
                        tool_call=prepared.tool_call,
                        args=prepared.args,
                        result=result,
                        is_error=is_error,
                        context=current_context,
                    ),
                    signal,
                )
            )
            if after_result is not None:
                result = _apply_after_tool_call_result(result, after_result)
                if after_result.is_error is not UNSET:
                    is_error = bool(after_result.is_error)
        except Exception as exc:
            result = _create_error_tool_result(str(exc))
            is_error = True

    return await _emit_tool_call_outcome(prepared.tool_call, result, is_error, emit)


def _apply_after_tool_call_result(
    result: AgentToolResult,
    override: AfterToolCallResult,
) -> AgentToolResult:
    content = result.content
    if override.content is not UNSET:
        content = cast(list[TextContent | ImageContent], override.content)
    details = result.details if override.details is UNSET else override.details
    return AgentToolResult(content=content, details=details)


def _create_error_tool_result(message: str) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text=message)], details={})


async def _emit_tool_call_outcome(
    tool_call: ToolCall,
    result: AgentToolResult,
    is_error: bool,
    emit: AgentEventSink,
) -> ToolResultMessage:
    await maybe_await(
        emit(
            ToolExecutionEndEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=deepcopy(result),
                is_error=is_error,
            )
        )
    )

    tool_result_message = ToolResultMessage(
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=deepcopy(result.content),
        details=deepcopy(result.details),
        is_error=is_error,
        timestamp=_timestamp_ms(),
    )
    await maybe_await(emit(MessageStartEvent(message=deepcopy(tool_result_message))))
    await maybe_await(emit(MessageEndEvent(message=deepcopy(tool_result_message))))
    return tool_result_message


async def _get_pending_messages(getter) -> list[AgentMessage]:
    if getter is None:
        return []
    messages = await maybe_await(getter())
    return list(messages)


def _normalize_thinking_budgets(
    budgets: dict[ReasoningLevel, int] | None,
) -> dict[LlmReasoningLevel, int] | None:
    if budgets is None:
        return None

    normalized: dict[LlmReasoningLevel, int] = {}
    for key, value in budgets.items():
        resolved = resolve_llm_reasoning_level(key)
        if resolved is None:
            continue
        normalized[resolved] = value
    return normalized


def _message_role(message: AgentMessage) -> str:
    return message.role


def _clone_message(message: AgentMessage) -> AgentMessage:
    try:
        return deepcopy(message)
    except Exception:
        return message


def _timestamp_ms() -> int:
    return int(time.time() * 1000)
