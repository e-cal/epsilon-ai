from __future__ import annotations

import asyncio
from typing import cast

import httpx
import pytest

from epsilon.llm import Context, SimpleStreamOptions, Tool, UserMessage
from epsilon.llm.models import get_model
from epsilon.llm.providers.openai_codex_responses import (
    OpenAICodexResponsesOptions,
    build_openai_codex_responses_payload,
    clamp_openai_codex_reasoning_effort,
    normalize_openai_codex_status,
    parse_openai_codex_error_response,
    resolve_openai_codex_url,
    stream_simple_openai_codex_responses,
)


def test_build_openai_codex_responses_payload_uses_instructions_and_null_strict() -> None:
    model = get_model("openai-codex", "gpt-5.3-codex")
    context = Context(
        system_prompt="You are helpful.",
        messages=[UserMessage(content="hello", timestamp=1)],
        tools=[
            Tool(
                name="get_time",
                description="Get the current time.",
                parameters={"type": "object", "properties": {}},
            )
        ],
    )

    payload = build_openai_codex_responses_payload(
        model,
        context,
        OpenAICodexResponsesOptions(
            session_id="session-1",
            reasoning_effort="minimal",
            text_verbosity="high",
        ),
    )

    assert payload["instructions"] == "You are helpful."
    assert payload["prompt_cache_key"] == "session-1"
    assert payload["text"] == {"verbosity": "high"}
    assert payload["reasoning"] == {"effort": "low", "summary": "auto"}
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "get_time",
            "description": "Get the current time.",
            "parameters": {"type": "object", "properties": {}},
            "strict": None,
        }
    ]

    input_payload = payload["input"]
    assert isinstance(input_payload, list)
    assert input_payload == [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}]


def test_clamp_openai_codex_reasoning_effort_matches_upstream() -> None:
    assert clamp_openai_codex_reasoning_effort("gpt-5.3-codex", "minimal") == "low"
    assert clamp_openai_codex_reasoning_effort("gpt-5.1", "xhigh") == "high"
    assert clamp_openai_codex_reasoning_effort("gpt-5.1-codex-mini", "low") == "medium"


def test_resolve_openai_codex_url_appends_codex_responses_path() -> None:
    assert resolve_openai_codex_url("") == "https://chatgpt.com/backend-api/codex/responses"
    assert (
        resolve_openai_codex_url("https://chatgpt.com/backend-api")
        == "https://chatgpt.com/backend-api/codex/responses"
    )
    assert (
        resolve_openai_codex_url("https://chatgpt.com/backend-api/codex")
        == "https://chatgpt.com/backend-api/codex/responses"
    )


def test_normalize_openai_codex_status_filters_unknown_values() -> None:
    assert normalize_openai_codex_status("completed") == "completed"
    assert normalize_openai_codex_status("weird") is None


def test_parse_openai_codex_error_response_formats_usage_limit_message() -> None:
    message, friendly = parse_openai_codex_error_response(
        429,
        "Too Many Requests",
        '{"error":{"code":"usage_limit_reached","message":"rate limited","plan_type":"PLUS"}}',
    )

    assert message == "rate limited"
    assert friendly == "You have hit your ChatGPT usage limit (plus plan)."


def test_stream_simple_openai_codex_responses_builds_provider_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_stream_openai_codex_responses(model, context, options=None):
        captured["model"] = model
        captured["context"] = context
        captured["options"] = options
        return object()

    monkeypatch.setattr(
        "epsilon.llm.providers.openai_codex_responses.stream_openai_codex_responses",
        fake_stream_openai_codex_responses,
    )

    model = get_model("openai-codex", "gpt-5.1")
    context = Context(messages=[UserMessage(content="hello", timestamp=1)])

    stream_simple_openai_codex_responses(
        model,
        context,
        SimpleStreamOptions(api_key="token"),
    )

    options = captured["options"]
    assert isinstance(options, OpenAICodexResponsesOptions)
    assert options.api_key == "token"


@pytest.mark.asyncio
async def test_send_openai_codex_request_aborts_mid_request() -> None:
    from epsilon.llm.providers.openai_codex_responses import _send_openai_codex_request
    from epsilon.llm.runtime import RequestAbortedError

    class FakeClient:
        async def send(self, request, *, stream: bool):
            del request, stream
            await asyncio.sleep(10)
            raise AssertionError("request should have been cancelled")

    signal = asyncio.Event()
    task = asyncio.create_task(
        _send_openai_codex_request(
            cast(httpx.AsyncClient, FakeClient()),
            httpx.Request("POST", "https://example.test"),
            signal,
        )
    )

    await asyncio.sleep(0)
    signal.set()

    with pytest.raises(RequestAbortedError, match="Request was aborted"):
        await task
