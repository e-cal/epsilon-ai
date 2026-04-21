from __future__ import annotations

import pytest

from epsilon.llm import Context, SimpleStreamOptions, StreamOptions, UserMessage
from epsilon.llm.event_stream import create_assistant_message_event_stream
from epsilon.llm.models import get_model
from epsilon.llm.providers.anthropic import AnthropicOptions, build_anthropic_payload
from epsilon.llm.providers.azure_openai_responses import (
    AzureOpenAIResponsesOptions,
    build_azure_openai_responses_payload,
    stream_simple_azure_openai_responses,
)
from epsilon.llm.providers.openai_responses import (
    OpenAIResponsesOptions,
    _run_openai_responses,
    build_openai_responses_payload,
    stream_simple_openai_responses,
)
from epsilon.llm.providers.simple_options import coerce_stream_options, stream_options_to_kwargs


def test_build_openai_responses_payload_accepts_plain_stream_options() -> None:
    model = get_model("openai", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_openai_responses_payload(model, context, StreamOptions())

    assert payload["model"] == "gpt-4o-mini"
    assert "service_tier" not in payload


def test_build_azure_openai_responses_payload_accepts_plain_stream_options() -> None:
    model = get_model("azure-openai-responses", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_azure_openai_responses_payload(model, context, StreamOptions())

    assert payload["model"] == "gpt-4o-mini"
    assert "reasoning" not in payload


def test_build_anthropic_payload_accepts_plain_stream_options() -> None:
    model = get_model("anthropic", "claude-sonnet-4-5")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_anthropic_payload(model, context, StreamOptions())

    assert payload["model"] == "claude-sonnet-4-5"
    assert "thinking" not in payload


def test_coerce_stream_options_copies_shared_fields_into_provider_options() -> None:
    options = StreamOptions(temperature=0.25, max_tokens=123, session_id="session-1")

    openai_options = coerce_stream_options(options, OpenAIResponsesOptions)
    azure_options = coerce_stream_options(options, AzureOpenAIResponsesOptions)
    anthropic_options = coerce_stream_options(options, AnthropicOptions)

    assert openai_options is not None
    assert azure_options is not None
    assert anthropic_options is not None
    assert openai_options.temperature == 0.25
    assert azure_options.max_tokens == 123
    assert anthropic_options.session_id == "session-1"


def test_stream_options_to_kwargs_supports_simple_stream_conversion() -> None:
    base = StreamOptions(temperature=0.5, max_tokens=256, session_id="session-2")

    openai_kwargs = stream_options_to_kwargs(base, OpenAIResponsesOptions)
    azure_kwargs = stream_options_to_kwargs(base, AzureOpenAIResponsesOptions)

    assert openai_kwargs == {
        "temperature": 0.5,
        "max_tokens": 256,
        "signal": None,
        "api_key": None,
        "transport": None,
        "cache_retention": None,
        "session_id": "session-2",
        "on_payload": None,
        "headers": None,
        "max_retry_delay_ms": None,
        "metadata": None,
    }
    assert azure_kwargs["session_id"] == "session-2"


def test_stream_simple_openai_responses_builds_provider_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_stream_openai_responses(model, context, options=None):
        captured["model"] = model
        captured["context"] = context
        captured["options"] = options
        return object()

    monkeypatch.setattr(
        "epsilon.llm.providers.openai_responses.stream_openai_responses",
        fake_stream_openai_responses,
    )

    model = get_model("openai", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    stream_simple_openai_responses(
        model,
        context,
        SimpleStreamOptions(api_key="test", temperature=0.4, session_id="session-3"),
    )

    options = captured["options"]
    assert isinstance(options, OpenAIResponsesOptions)
    assert options.temperature == 0.4
    assert options.session_id == "session-3"


def test_stream_simple_azure_openai_responses_builds_provider_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_stream_azure_openai_responses(model, context, options=None):
        captured["model"] = model
        captured["context"] = context
        captured["options"] = options
        return object()

    monkeypatch.setattr(
        "epsilon.llm.providers.azure_openai_responses.stream_azure_openai_responses",
        fake_stream_azure_openai_responses,
    )

    model = get_model("azure-openai-responses", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    stream_simple_azure_openai_responses(
        model,
        context,
        SimpleStreamOptions(api_key="test", temperature=0.4, session_id="session-4"),
    )

    options = captured["options"]
    assert isinstance(options, AzureOpenAIResponsesOptions)
    assert options.temperature == 0.4
    assert options.session_id == "session-4"


@pytest.mark.asyncio
async def test_run_openai_responses_preserves_error_message_from_terminal_status(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeResponseStream:
        async def __aenter__(self) -> FakeResponse:
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeAsyncClient:
        def __init__(self, *, timeout=None) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        def stream(self, method, url, *, headers, json):
            return FakeResponseStream()

    async def fake_process(events, output, stream, model, *, options=None) -> None:
        output.stop_reason = "error"
        output.error_message = "insufficient_quota: You exceeded your current quota."

    monkeypatch.setattr(
        "epsilon.llm.providers.openai_responses.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "epsilon.llm.providers.openai_responses.process_openai_responses_event_stream",
        fake_process,
    )

    model = get_model("openai", "gpt-5-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])
    stream = create_assistant_message_event_stream()

    await _run_openai_responses(stream, model, context, OpenAIResponsesOptions(api_key="test"))

    message = await stream.result()
    assert message.stop_reason == "error"
    assert message.error_message == "insufficient_quota: You exceeded your current quota."
