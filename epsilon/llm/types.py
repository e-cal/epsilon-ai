from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, cast

if TYPE_CHECKING:
    from .event_stream import AssistantMessageEventStream


type Api = str
type Provider = str
type KnownApi = Literal[
    "openai-completions",
    "mistral-conversations",
    "openai-responses",
    "foundry",
    "azure-openai-responses",
    "openai-codex-responses",
    "anthropic-messages",
    "bedrock-converse-stream",
    "google-generative-ai",
    "google-gemini-cli",
    "google-vertex",
]
type KnownProvider = Literal[
    "amazon-bedrock",
    "anthropic",
    "google",
    "google-gemini-cli",
    "google-antigravity",
    "google-vertex",
    "openai",
    "foundry",
    "azure-openai-responses",
    "codex",
    "openai-codex",
    "github-copilot",
    "xai",
    "groq",
    "cerebras",
    "openrouter",
    "vercel-ai-gateway",
    "zai",
    "mistral",
    "minimax",
    "minimax-cn",
    "huggingface",
    "opencode",
    "opencode-go",
    "kimi-coding",
]
REASONING_LEVELS = ("none", "minimal", "low", "medium", "high", "max", "xhigh")
type ReasoningLevel = Literal["none", "minimal", "low", "medium", "high", "max", "xhigh"]
type ProviderReasoningLevel = Literal["minimal", "low", "medium", "high", "xhigh"]
type CacheRetention = Literal["none", "short", "long"]
type Transport = Literal["sse", "websocket", "auto"]
type StopReason = Literal["stop", "length", "toolUse", "error", "aborted"]
type JSONPrimitive = bool | int | float | str | None
type JSONValue = JSONPrimitive | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(slots=True)
class OpenAICompletionsCompat:
    supports_store: bool | None = None
    supports_developer_role: bool | None = None
    supports_reasoning_effort: bool | None = None
    reasoning_effort_map: dict[ReasoningLevel, str] | None = None
    supports_usage_in_streaming: bool | None = None
    max_tokens_field: Literal["max_completion_tokens", "max_tokens"] | None = None
    requires_tool_result_name: bool | None = None
    requires_assistant_after_tool_result: bool | None = None
    requires_thinking_as_text: bool | None = None
    thinking_format: Literal["openai", "openrouter", "zai", "qwen", "qwen-chat-template"] | None = (
        None
    )
    open_router_routing: dict[str, list[str]] | None = None
    vercel_gateway_routing: dict[str, list[str]] | None = None
    zai_tool_stream: bool | None = None
    supports_strict_mode: bool | None = None


@dataclass(slots=True)
class OpenAIResponsesCompat:
    pass


@dataclass(slots=True)
class Cost:
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    total: float = 0.0


@dataclass(slots=True)
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: Cost = field(default_factory=Cost)


@dataclass(slots=True)
class Model:
    id: str
    name: str
    api: Api
    provider: Provider
    base_url: str = ""
    reasoning: bool = False
    input: list[Literal["text", "image"]] = field(default_factory=lambda: ["text"])
    cost: Cost = field(default_factory=Cost)
    context_window: int = 0
    max_tokens: int = 0
    headers: dict[str, str] | None = None
    compat: OpenAICompletionsCompat | OpenAIResponsesCompat | None = None


@dataclass(slots=True)
class StreamOptions:
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    signal: object | None = None
    api_key: str | None = None
    transport: Transport | None = None
    cache_retention: CacheRetention | None = None
    session_id: str | None = None
    on_payload: Callable[[object, Model], object | Awaitable[object | None] | None] | None = None
    headers: dict[str, str] | None = None
    max_retry_delay_ms: int | None = None
    metadata: JSONObject | None = None
    reasoning: ReasoningLevel | None = None
    thinking_budgets: dict[ReasoningLevel, int] | None = None
    text_verbosity: Literal["low", "medium", "high"] | None = None
    text_format: JSONObject | None = None
    store: bool | None = None


def resolve_reasoning_level(level: ReasoningLevel | None) -> ProviderReasoningLevel | None:
    if level in {None, "none"}:
        return None
    if level in {"max", "xhigh"}:
        return "xhigh"
    return cast(ProviderReasoningLevel, level)


@dataclass(slots=True)
class TextContent:
    type: Literal["text"] = "text"
    text: str = ""
    text_signature: str | None = None


@dataclass(slots=True)
class ThinkingContent:
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    thinking_signature: str | None = None
    redacted: bool = False


@dataclass(slots=True)
class ImageContent:
    type: Literal["image"] = "image"
    data: str = ""
    mime_type: str = ""


@dataclass(slots=True)
class ToolCall:
    type: Literal["toolCall"] = "toolCall"
    id: str = ""
    name: str = ""
    arguments: JSONObject = field(default_factory=dict)
    thought_signature: str | None = None


type ContentBlock = TextContent | ThinkingContent | ToolCall
type UserContentBlock = TextContent | ImageContent
type ToolResultContentBlock = TextContent | ImageContent


@dataclass(slots=True)
class UserMessage:
    role: Literal["user"] = "user"
    content: str | list[UserContentBlock] = ""
    timestamp: int = 0


@dataclass(slots=True)
class AssistantMessage:
    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock] = field(default_factory=list)
    api: Api = ""
    provider: Provider = ""
    model: str = ""
    response_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    stop_reason: StopReason = "stop"
    error_message: str | None = None
    timestamp: int = 0


@dataclass(slots=True)
class ToolResultMessage:
    role: Literal["toolResult"] = "toolResult"
    tool_call_id: str = ""
    tool_name: str = ""
    content: list[ToolResultContentBlock] = field(default_factory=list)
    details: object | None = None
    is_error: bool = False
    timestamp: int = 0


type Message = UserMessage | AssistantMessage | ToolResultMessage


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: JSONObject


@dataclass(slots=True)
class Context:
    messages: list[Message]
    system_prompt: str | None = None
    tools: list[Tool] | None = None


@dataclass(slots=True)
class StartEvent:
    type: Literal["start"] = "start"
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class TextStartEvent:
    type: Literal["text_start"] = "text_start"
    content_index: int = 0
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class TextDeltaEvent:
    type: Literal["text_delta"] = "text_delta"
    content_index: int = 0
    delta: str = ""
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class TextEndEvent:
    type: Literal["text_end"] = "text_end"
    content_index: int = 0
    content: str = ""
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ThinkingStartEvent:
    type: Literal["thinking_start"] = "thinking_start"
    content_index: int = 0
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ThinkingDeltaEvent:
    type: Literal["thinking_delta"] = "thinking_delta"
    content_index: int = 0
    delta: str = ""
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ThinkingEndEvent:
    type: Literal["thinking_end"] = "thinking_end"
    content_index: int = 0
    content: str = ""
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ToolCallStartEvent:
    type: Literal["toolcall_start"] = "toolcall_start"
    content_index: int = 0
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ToolCallDeltaEvent:
    type: Literal["toolcall_delta"] = "toolcall_delta"
    content_index: int = 0
    delta: str = ""
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ToolCallEndEvent:
    type: Literal["toolcall_end"] = "toolcall_end"
    content_index: int = 0
    tool_call: ToolCall = field(default_factory=ToolCall)
    partial: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class DoneEvent:
    type: Literal["done"] = "done"
    reason: Literal["stop", "length", "toolUse"] = "stop"
    message: AssistantMessage = field(default_factory=AssistantMessage)


@dataclass(slots=True)
class ErrorEvent:
    type: Literal["error"] = "error"
    reason: Literal["aborted", "error"] = "error"
    error: AssistantMessage = field(default_factory=AssistantMessage)


type AssistantMessageEvent = (
    StartEvent
    | TextStartEvent
    | TextDeltaEvent
    | TextEndEvent
    | ThinkingStartEvent
    | ThinkingDeltaEvent
    | ThinkingEndEvent
    | ToolCallStartEvent
    | ToolCallDeltaEvent
    | ToolCallEndEvent
    | DoneEvent
    | ErrorEvent
)


class StreamFunction(Protocol):
    def __call__(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantMessageEventStream: ...
