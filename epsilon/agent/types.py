from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast, runtime_checkable

from ..llm.event_stream import AssistantMessageEventStream
from ..llm.types import (
    AssistantMessage,
    AssistantMessageEvent,
    CacheRetention,
    Context,
    ImageContent,
    JSONObject,
    Message,
    Model,
    SimpleStreamOptions,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Transport,
)
from ..llm.types import (
    ThinkingLevel as LlmThinkingLevel,
)
from ..llm.types import (
    Tool as LlmTool,
)

type ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]
type ToolExecutionMode = Literal["sequential", "parallel"]
type QueueMode = Literal["all", "one-at-a-time"]

UNSET = object()


class AbortSignal:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    def abort(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


@runtime_checkable
class SupportsAgentMessage(Protocol):
    role: str
    timestamp: int


type AgentMessage = Message | SupportsAgentMessage
type StreamFn = Callable[[Model, Context, SimpleStreamOptions | None], AssistantMessageEventStream]
type ConvertToLlmFn = Callable[[list[AgentMessage]], list[Message] | Awaitable[list[Message]]]
type TransformContextFn = Callable[
    [list[AgentMessage], AbortSignal | None],
    list[AgentMessage] | Awaitable[list[AgentMessage]],
]
type GetApiKeyFn = Callable[[str], str | None | Awaitable[str | None]]
type PendingMessagesFn = Callable[[], list[AgentMessage] | Awaitable[list[AgentMessage]]]


@dataclass(slots=True)
class AgentToolResult:
    content: list[TextContent | ImageContent]
    details: object


type AgentToolUpdateCallback = Callable[[AgentToolResult], None]
type PrepareArgumentsFn = Callable[[object], object]
type ExecuteToolFn = Callable[
    [str, object, AbortSignal | None, AgentToolUpdateCallback | None],
    Awaitable[AgentToolResult],
]


@dataclass(slots=True)
class AgentTool:
    name: str
    label: str
    description: str
    parameters: JSONObject
    execute: ExecuteToolFn
    prepare_arguments: PrepareArgumentsFn | None = None

    def to_llm_tool(self) -> LlmTool:
        return LlmTool(name=self.name, description=self.description, parameters=self.parameters)


@dataclass(slots=True)
class BeforeToolCallResult:
    block: bool = False
    reason: str | None = None


@dataclass(slots=True)
class AfterToolCallResult:
    content: list[TextContent | ImageContent] | object = field(default=UNSET)
    details: object = field(default=UNSET)
    is_error: bool | object = field(default=UNSET)


@dataclass(slots=True)
class AgentContext:
    system_prompt: str
    messages: list[AgentMessage]
    tools: list[AgentTool] | None = None


@dataclass(slots=True)
class BeforeToolCallContext:
    assistant_message: AssistantMessage
    tool_call: ToolCall
    args: object
    context: AgentContext


@dataclass(slots=True)
class AfterToolCallContext:
    assistant_message: AssistantMessage
    tool_call: ToolCall
    args: object
    result: AgentToolResult
    is_error: bool
    context: AgentContext


type BeforeToolCallFn = Callable[
    [BeforeToolCallContext, AbortSignal | None],
    BeforeToolCallResult | None | Awaitable[BeforeToolCallResult | None],
]
type AfterToolCallFn = Callable[
    [AfterToolCallContext, AbortSignal | None],
    AfterToolCallResult | None | Awaitable[AfterToolCallResult | None],
]


@dataclass(slots=True, kw_only=True)
class AgentLoopConfig:
    model: Model
    convert_to_llm: ConvertToLlmFn
    transform_context: TransformContextFn | None = None
    get_api_key: GetApiKeyFn | None = None
    get_steering_messages: PendingMessagesFn | None = None
    get_follow_up_messages: PendingMessagesFn | None = None
    tool_execution: ToolExecutionMode = "parallel"
    before_tool_call: BeforeToolCallFn | None = None
    after_tool_call: AfterToolCallFn | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    api_key: str | None = None
    transport: Transport | None = None
    cache_retention: CacheRetention | None = None
    session_id: str | None = None
    on_payload: Callable[[object, Model], object | Awaitable[object | None] | None] | None = None
    headers: dict[str, str] | None = None
    max_retry_delay_ms: int | None = None
    metadata: JSONObject | None = None
    reasoning: ThinkingLevel | None = None
    thinking_budgets: dict[ThinkingLevel, int] | None = None


@dataclass(slots=True)
class AgentInitialState:
    system_prompt: str = ""
    model: Model | None = None
    thinking_level: ThinkingLevel = "off"
    tools: list[AgentTool] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)


@dataclass(slots=True)
class AgentStartEvent:
    type: Literal["agent_start"] = "agent_start"


@dataclass(slots=True)
class AgentEndEvent:
    messages: list[AgentMessage]
    type: Literal["agent_end"] = "agent_end"


@dataclass(slots=True)
class TurnStartEvent:
    type: Literal["turn_start"] = "turn_start"


@dataclass(slots=True)
class TurnEndEvent:
    message: AgentMessage
    tool_results: list[ToolResultMessage]
    type: Literal["turn_end"] = "turn_end"


@dataclass(slots=True)
class MessageStartEvent:
    message: AgentMessage
    type: Literal["message_start"] = "message_start"


@dataclass(slots=True)
class MessageUpdateEvent:
    message: AgentMessage
    assistant_message_event: AssistantMessageEvent
    type: Literal["message_update"] = "message_update"


@dataclass(slots=True)
class MessageEndEvent:
    message: AgentMessage
    type: Literal["message_end"] = "message_end"


@dataclass(slots=True)
class ToolExecutionStartEvent:
    tool_call_id: str
    tool_name: str
    args: object
    type: Literal["tool_execution_start"] = "tool_execution_start"


@dataclass(slots=True)
class ToolExecutionUpdateEvent:
    tool_call_id: str
    tool_name: str
    args: object
    partial_result: AgentToolResult
    type: Literal["tool_execution_update"] = "tool_execution_update"


@dataclass(slots=True)
class ToolExecutionEndEvent:
    tool_call_id: str
    tool_name: str
    result: AgentToolResult
    is_error: bool
    type: Literal["tool_execution_end"] = "tool_execution_end"


type AgentEvent = (
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent
)


def normalize_reasoning_level(value: ThinkingLevel | None) -> LlmThinkingLevel | None:
    if value in {None, "off"}:
        return None
    return cast(LlmThinkingLevel, value)
