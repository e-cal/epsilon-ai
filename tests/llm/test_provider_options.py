from __future__ import annotations

from importlib import import_module
from typing import cast

import httpx
import pytest

from epsilon.llm import Context, Model, StreamOptions, UserMessage
from epsilon.llm.event_stream import create_assistant_message_event_stream
from epsilon.llm.models import get_model
from epsilon.llm.providers.anthropic import AnthropicOptions, build_anthropic_payload
from epsilon.llm.providers.azure_openai_responses import AzureOpenAIResponsesOptions
from epsilon.llm.providers.foundry import (
    FoundryOptions,
    _build_foundry_inner_stream,
    _build_foundry_openai_options,
    _resolve_foundry_options,
    build_foundry_responses_payload,
)
from epsilon.llm.providers.openai_responses import (
    OpenAIResponsesOptions,
    _resolve_openai_responses_options,
    _run_openai_responses,
    build_openai_responses_payload,
)
from epsilon.llm.providers.openai_responses_shared import (
    process_openai_responses_event_stream,
)
from epsilon.llm.providers.shared import create_empty_assistant_message
from epsilon.llm.providers.simple_options import coerce_stream_options, stream_options_to_kwargs

llm_stream_module = import_module("epsilon.llm.stream")


def test_build_openai_responses_payload_accepts_plain_stream_options() -> None:
    model = get_model("openai", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_openai_responses_payload(model, context, StreamOptions())

    assert payload["model"] == "gpt-4o-mini"
    assert "service_tier" not in payload


def test_build_foundry_responses_payload_accepts_plain_stream_options(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("foundry", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_foundry_responses_payload(model, context, StreamOptions())

    assert payload["model"] == "gpt-4o-mini"
    assert "reasoning" not in payload


def test_build_foundry_responses_payload_includes_text_verbosity(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("foundry", "gpt-5-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_foundry_responses_payload(
        model,
        context,
        StreamOptions(
            metadata={"purpose": "router"},
            text_format={"type": "text"},
            text_verbosity="low",
            top_p=0.5,
        ),
    )

    assert payload["metadata"] == {"purpose": "router"}
    assert payload["text"] == {"verbosity": "low", "format": {"type": "text"}}
    assert payload["top_p"] == 0.5


def test_build_foundry_responses_payload_omits_unsupported_reasoning_none(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("foundry", "gpt-5-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_foundry_responses_payload(model, context, StreamOptions())

    assert "reasoning" not in payload
    assert "include" not in payload


def test_build_foundry_responses_payload_rejects_claude_models(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT", "epsilon-foundry")
    model = get_model("foundry", "claude-sonnet-4-6")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    with pytest.raises(
        ValueError,
        match=(
            r"Foundry Responses payloads are only valid for OpenAI-compatible Foundry models\."
        ),
    ):
        build_foundry_responses_payload(model, context, StreamOptions())


def test_build_anthropic_payload_accepts_plain_stream_options() -> None:
    model = get_model("anthropic", "claude-sonnet-4-5")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    payload = build_anthropic_payload(model, context, StreamOptions())

    assert payload["model"] == "claude-sonnet-4-5"
    assert "thinking" not in payload


def test_stream_anthropic_maps_plain_stream_options_to_explicit_thinking_disable(
    monkeypatch,
) -> None:
    del monkeypatch

    from epsilon.llm.providers.anthropic import _resolve_anthropic_options

    model = get_model("anthropic", "claude-sonnet-4-5")

    options = _resolve_anthropic_options(model, StreamOptions())
    assert isinstance(options, AnthropicOptions)
    assert options.thinking_enabled is False


def test_stream_anthropic_treats_none_reasoning_as_disabled() -> None:
    from epsilon.llm.providers.anthropic import _resolve_anthropic_options

    model = get_model("anthropic", "claude-sonnet-4-5")

    options = _resolve_anthropic_options(model, StreamOptions(reasoning="none"))
    assert isinstance(options, AnthropicOptions)
    assert options.thinking_enabled is False


def test_coerce_stream_options_copies_shared_fields_into_provider_options() -> None:
    options = StreamOptions(temperature=0.25, max_tokens=123, session_id="session-1")

    openai_options = coerce_stream_options(options, OpenAIResponsesOptions)
    foundry_options = coerce_stream_options(options, FoundryOptions)
    anthropic_options = coerce_stream_options(options, AnthropicOptions)

    assert openai_options is not None
    assert foundry_options is not None
    assert anthropic_options is not None
    assert openai_options.temperature == 0.25
    assert foundry_options.max_tokens == 123
    assert anthropic_options.session_id == "session-1"


def test_stream_options_to_kwargs_supports_simple_stream_conversion() -> None:
    base = StreamOptions(temperature=0.5, max_tokens=256, session_id="session-2")

    openai_kwargs = stream_options_to_kwargs(base, OpenAIResponsesOptions)
    foundry_kwargs = stream_options_to_kwargs(base, FoundryOptions)

    assert openai_kwargs == {
        "temperature": 0.5,
        "top_p": None,
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
        "reasoning": None,
        "thinking_budgets": None,
        "text_verbosity": None,
        "text_format": None,
        "store": None,
    }
    assert foundry_kwargs["session_id"] == "session-2"
    assert "foundry_project" not in foundry_kwargs


def test_stream_openai_responses_maps_plain_stream_options_to_provider_options() -> None:
    model = get_model("openai", "gpt-5.4")
    options = _resolve_openai_responses_options(
        model,
        StreamOptions(api_key="test", temperature=0.4, session_id="session-3", reasoning="max"),
    )

    assert isinstance(options, OpenAIResponsesOptions)
    assert options.temperature == 0.4
    assert options.session_id == "session-3"
    assert options.reasoning_effort == "xhigh"


def test_stream_openai_responses_accepts_xhigh_reasoning_alias() -> None:
    model = get_model("openai", "gpt-5.4")
    options = _resolve_openai_responses_options(
        model,
        StreamOptions(api_key="test", reasoning="xhigh"),
    )

    assert isinstance(options, OpenAIResponsesOptions)
    assert options.reasoning_effort == "xhigh"


def test_openai_codex_models_use_canonical_provider_name() -> None:
    model = get_model("openai-codex", "gpt-5.4")

    assert model.provider == "openai-codex"


def test_stream_foundry_maps_plain_stream_options_to_openai_provider_options() -> None:
    model = get_model("foundry", "gpt-5.4")
    options = _resolve_foundry_options(
        model,
        StreamOptions(api_key="test", temperature=0.4, session_id="session-4", reasoning="max"),
    )

    assert isinstance(options, FoundryOptions)
    assert options.temperature == 0.4
    assert options.session_id == "session-4"
    assert options.reasoning_effort == "xhigh"


def test_stream_foundry_accepts_xhigh_reasoning_alias() -> None:
    model = get_model("foundry", "gpt-5.4")
    options = _resolve_foundry_options(
        model,
        StreamOptions(api_key="test", reasoning="xhigh"),
    )

    assert isinstance(options, FoundryOptions)
    assert options.reasoning_effort == "xhigh"


def test_stream_foundry_rejects_too_small_openai_max_tokens() -> None:
    model = get_model("foundry", "gpt-5-mini")

    with pytest.raises(
        ValueError,
        match=(
            r"Foundry OpenAI-compatible models require max_tokens >= 16; "
            r"got 4 for foundry/gpt-5-mini\."
        ),
    ):
        _build_foundry_openai_options(
            model,
            FoundryOptions(foundry_project="epsilon-foundry", max_tokens=4),
        )


def test_stream_foundry_rejects_explicit_none_reasoning_effort() -> None:
    model = get_model("foundry", "gpt-5-mini")

    with pytest.raises(
        ValueError,
        match=(
            r"Foundry OpenAI-compatible models do not support reasoning='none'; "
            r"omit reasoning or use one of minimal/low/medium/high "
            r"for foundry/gpt-5-mini\."
        ),
    ):
        _build_foundry_openai_options(
            model,
            FoundryOptions(foundry_project="epsilon-foundry", reasoning_effort="none"),
        )


def test_stream_foundry_rejects_stream_reasoning_none() -> None:
    model = get_model("foundry", "gpt-5-mini")
    options = _resolve_foundry_options(
        model,
        StreamOptions(api_key="test", reasoning="none"),
    )

    assert isinstance(options, FoundryOptions)
    with pytest.raises(
        ValueError,
        match=(
            r"Foundry OpenAI-compatible models do not support reasoning='none'; "
            r"omit reasoning or use one of minimal/low/medium/high "
            r"for foundry/gpt-5-mini\."
        ),
    ):
        _build_foundry_openai_options(model, options)


def test_stream_foundry_maps_plain_stream_options_to_anthropic_provider_options() -> None:
    model = get_model("foundry", "claude-sonnet-4-6")
    options = _resolve_foundry_options(
        model,
        StreamOptions(api_key="test", reasoning="medium"),
    )

    assert isinstance(options, FoundryOptions)
    assert options.thinking_enabled is True
    assert options.effort == "medium"


def test_stream_foundry_maps_nonadaptive_anthropic_options_without_duplicate_max_tokens() -> None:
    model = get_model("foundry", "claude-sonnet-4-5")
    options = _resolve_foundry_options(
        model,
        StreamOptions(api_key="test", max_tokens=32, reasoning="minimal"),
    )

    assert isinstance(options, FoundryOptions)
    assert options.thinking_enabled is True
    assert options.max_tokens is not None
    assert options.max_tokens > 32
    assert options.thinking_budget_tokens is not None


def test_build_foundry_inner_stream_routes_gpt_models_to_openai_transport(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_stream_azure_openai_responses(model, context, options=None):
        captured["model"] = model
        captured["context"] = context
        captured["options"] = options
        return sentinel

    monkeypatch.setattr(
        "epsilon.llm.providers.foundry.stream_azure_openai_responses",
        fake_stream_azure_openai_responses,
    )

    model = get_model("foundry", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    stream = _build_foundry_inner_stream(
        model,
        context,
        FoundryOptions(foundry_project="epsilon-foundry"),
    )

    assert stream is sentinel
    inner_model = cast(Model, captured["model"])
    inner_options = cast(AzureOpenAIResponsesOptions, captured["options"])
    assert inner_model.provider == "foundry"
    assert inner_model.api == "foundry"
    assert inner_model.base_url == "https://epsilon-foundry.openai.azure.com/openai/v1"
    assert inner_options.azure_deployment_name == "gpt-4o-mini"


def test_build_foundry_inner_stream_routes_claude_models_to_anthropic_transport(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_stream_anthropic(model, context, options=None):
        captured["model"] = model
        captured["context"] = context
        captured["options"] = options
        return sentinel

    monkeypatch.setattr(
        "epsilon.llm.providers.foundry.stream_anthropic",
        fake_stream_anthropic,
    )

    model = get_model("foundry", "claude-sonnet-4-6")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    stream = _build_foundry_inner_stream(
        model,
        context,
        FoundryOptions(foundry_project="epsilon-foundry"),
    )

    assert stream is sentinel
    inner_model = cast(Model, captured["model"])
    assert inner_model.provider == "foundry"
    assert inner_model.api == "foundry"
    assert inner_model.base_url == "https://epsilon-foundry.services.ai.azure.com/anthropic/v1"
    assert inner_model.id == "claude-sonnet-4-6"


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


@pytest.mark.asyncio
async def test_run_azure_openai_responses_includes_response_body_in_http_errors(
    monkeypatch,
) -> None:
    from epsilon.llm.providers.azure_openai_responses import _run_azure_openai_responses

    request = httpx.Request("POST", "https://example.test/responses?api-version=v1")
    response = httpx.Response(
        400,
        request=request,
        json={
            "error": {
                "message": "Invalid 'max_output_tokens': integer below minimum value.",
                "param": "max_output_tokens",
                "code": "integer_below_min_value",
            }
        },
    )

    class FakeResponseStream:
        async def __aenter__(self):
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeAsyncClient:
        def __init__(self, *, timeout=None) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        def stream(self, method, url, *, headers, json):
            return FakeResponseStream()

    monkeypatch.setattr(
        "epsilon.llm.providers.azure_openai_responses.httpx.AsyncClient",
        FakeAsyncClient,
    )

    model = get_model("foundry", "gpt-5-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])
    stream = create_assistant_message_event_stream()

    await _run_azure_openai_responses(
        stream,
        model,
        context,
        AzureOpenAIResponsesOptions(api_key="test", azure_base_url="https://example.test/openai/v1"),
    )

    message = await stream.result()
    assert message.stop_reason == "error"
    assert "Response body:" in (message.error_message or "")
    assert (
        "Invalid 'max_output_tokens': integer below minimum value."
        in (message.error_message or "")
    )


@pytest.mark.asyncio
async def test_openai_responses_failed_event_does_not_hide_following_error() -> None:
    async def events():
        yield {
            "type": "response.failed",
            "response": {"status": "failed", "error": None, "incomplete_details": None},
        }
        yield {
            "type": "error",
            "error": {
                "code": "too_many_requests",
                "message": "Too Many Requests",
            },
        }

    model = get_model("foundry", "gpt-5-mini")
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    stream = create_assistant_message_event_stream()

    with pytest.raises(RuntimeError, match="too_many_requests.*Too Many Requests"):
        await process_openai_responses_event_stream(events(), output, stream, model)


@pytest.mark.asyncio
async def test_openai_responses_failed_event_preserves_fallback_error() -> None:
    async def events():
        yield {
            "type": "response.failed",
            "response": {"status": "failed", "error": None, "incomplete_details": None},
        }

    model = get_model("foundry", "gpt-5-mini")
    output = create_empty_assistant_message(api=model.api, provider=model.provider, model=model.id)
    stream = create_assistant_message_event_stream()

    await process_openai_responses_event_stream(events(), output, stream, model)

    assert output.stop_reason == "error"
    assert output.error_message == "Unknown error (no error details in response)"


@pytest.mark.asyncio
async def test_run_anthropic_foundry_reports_missing_deployment_clearly(monkeypatch) -> None:
    from epsilon.llm.providers.anthropic import _run_anthropic

    request = httpx.Request("POST", "https://example.test/anthropic/v1/messages")
    response = httpx.Response(
        404,
        request=request,
        json={
            "error": {
                "code": "DeploymentNotFound",
                "message": "The API deployment claude-sonnet-4-5 does not exist.",
                "details": "The API deployment claude-sonnet-4-5 does not exist.",
            }
        },
    )

    class FakeResponseStream:
        async def __aenter__(self):
            raise httpx.HTTPStatusError("boom", request=request, response=response)

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeAsyncClient:
        def __init__(self, *, timeout=None) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        def stream(self, method, url, *, headers, json):
            return FakeResponseStream()

    monkeypatch.setattr(
        "epsilon.llm.providers.anthropic.httpx.AsyncClient",
        FakeAsyncClient,
    )

    model = get_model("foundry", "claude-sonnet-4-5")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])
    stream = create_assistant_message_event_stream()

    await _run_anthropic(
        stream,
        model,
        context,
        AnthropicOptions(api_key="test"),
    )

    message = await stream.result()
    assert message.stop_reason == "error"
    assert "Foundry deployment not found for foundry/claude-sonnet-4-5." in (
        message.error_message or ""
    )
    assert "FOUNDRY_DEPLOYMENT_NAME_MAP" in (message.error_message or "")


def test_public_stream_uses_simple_mapping_for_reasoning_options(monkeypatch) -> None:
    calls: list[str] = []

    class FakeProvider:
        def stream(self, model, context, options=None):
            del model, context, options
            calls.append("stream")
            return object()

    monkeypatch.setattr(llm_stream_module, "_resolve_api_provider", lambda _api: FakeProvider())

    model = get_model("openai", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    llm_stream_module.stream(model, context, StreamOptions(reasoning="medium"))

    assert calls == ["stream"]


def test_public_stream_uses_provider_path_for_plain_stream_options(monkeypatch) -> None:
    calls: list[str] = []

    class FakeProvider:
        def stream(self, model, context, options=None):
            del model, context, options
            calls.append("stream")
            return object()

    monkeypatch.setattr(llm_stream_module, "_resolve_api_provider", lambda _api: FakeProvider())

    model = get_model("openai", "gpt-4o-mini")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    llm_stream_module.stream(model, context, StreamOptions(temperature=0.2))

    assert calls == ["stream"]
