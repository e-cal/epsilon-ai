from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import epsilon.llm as llm
from epsilon.llm import AssistantMessage, Context, TextContent, ToolCall, Usage

DOCS_LLM_PATH = Path("/Users/ecal/projects/epsilon-ai/docs/modules/llm.md")


def _python_blocks(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    blocks: list[str] = []
    inside = False
    current: list[str] = []

    for line in lines:
        if line == "```python":
            inside = True
            current = []
            continue
        if line == "```" and inside:
            blocks.append("\n".join(current))
            inside = False
            continue
        if inside:
            current.append(line)

    return blocks


def _block_starting_with(path: Path, prefix: str) -> str:
    for block in _python_blocks(path):
        if block.startswith(prefix):
            return block
    raise AssertionError(f"No python block starting with {prefix!r} found in {path}")


@dataclass
class FakeStream:
    events: Sequence[object]
    final_message: AssistantMessage

    def __aiter__(self) -> FakeStream:
        self._index = 0
        return self

    async def __anext__(self) -> object:
        if self._index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self._index]
        self._index += 1
        return event

    async def result(self) -> AssistantMessage:
        return self.final_message


def test_llm_quickstart_example_runs_as_documented(monkeypatch, capsys) -> None:
    block = _block_starting_with(DOCS_LLM_PATH, "import asyncio\n\nfrom epsilon.llm import (")
    model = llm.get_model("openai", "gpt-4o-mini")
    final_message = AssistantMessage(
        content=[ToolCall(id="call_1", name="get_time", arguments={"timezone": "UTC"})],
        api=model.api,
        provider=model.provider,
        model=model.id,
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=1,
    )
    continuation = AssistantMessage(
        content=[TextContent(text="It is 2026-04-03 12:00:00 UTC.")],
        api=model.api,
        provider=model.provider,
        model=model.id,
        usage=Usage(),
        stop_reason="stop",
        timestamp=2,
    )
    stream_events = [
        SimpleNamespace(type="start", partial=final_message),
        SimpleNamespace(type="toolcall_end", tool_call=final_message.content[0]),
        SimpleNamespace(type="done", reason="toolUse"),
    ]

    monkeypatch.setattr(llm, "get_model", lambda provider, model_id: model)
    monkeypatch.setattr(
        llm,
        "stream",
        lambda _model, _context, _options=None: FakeStream(stream_events, final_message),
    )

    async def fake_complete_async(
        _model: object, _context: Context, _options: object | None = None
    ) -> AssistantMessage:
        return continuation

    monkeypatch.setattr(llm, "complete_async", fake_complete_async)

    namespace: dict[str, Any] = {}
    exec(block, namespace)

    output = capsys.readouterr().out
    assert "starting openai/gpt-4o-mini" in output
    assert "Tool call: get_time {'timezone': 'UTC'}" in output
    assert "Done: toolUse" in output


def test_llm_tool_definition_example_runs_as_documented() -> None:
    block = _block_starting_with(DOCS_LLM_PATH, "from epsilon.llm import Tool")

    namespace: dict[str, Any] = {}
    exec(block, namespace)

    tool = namespace["tool"]
    assert tool.name == "get_weather"
    assert tool.parameters["required"] == ["location"]


def test_llm_reasoning_example_runs_as_documented(monkeypatch) -> None:
    block = _block_starting_with(
        DOCS_LLM_PATH,
        "from epsilon.llm import Context, StreamOptions, complete, get_model",
    )
    model = llm.get_model("anthropic", "claude-sonnet-4-5")
    response = AssistantMessage(
        content=[TextContent(text="done")],
        api=model.api,
        provider=model.provider,
        model=model.id,
        usage=Usage(),
        stop_reason="stop",
        timestamp=1,
    )

    monkeypatch.setattr(llm, "get_model", lambda provider, model_id: model)

    def fake_complete(
        _model: object, _context: Context, _options: object | None = None
    ) -> AssistantMessage:
        return response

    monkeypatch.setattr(llm, "complete", fake_complete)

    namespace: dict[str, Any] = {}
    exec(block, namespace)


def test_llm_models_and_providers_example_runs_as_documented() -> None:
    block = _block_starting_with(
        DOCS_LLM_PATH, "from epsilon.llm import get_model, get_models, get_providers"
    )

    namespace: dict[str, Any] = {}
    exec(block, namespace)

    providers = namespace["providers"]
    openai_models = namespace["openai_models"]
    model = namespace["model"]
    assert "openai" in providers
    assert any(candidate.id == "gpt-5-mini" for candidate in openai_models)
    assert model.id == "gpt-5-mini"


def test_llm_reasoning_levels_runtime_export_is_easy_to_use() -> None:
    assert llm.REASONING_LEVELS == ("none", "minimal", "low", "medium", "high", "max", "xhigh")


def test_llm_faux_provider_example_runs_as_documented() -> None:
    block = _block_starting_with(
        DOCS_LLM_PATH,
        "from epsilon.llm.providers import faux_assistant_message, register_faux_provider",
    )

    namespace: dict[str, Any] = {}
    exec(block, namespace)

    registration = namespace["registration"]
    model = namespace["model"]
    assert model.provider.startswith("faux")
    registration.unregister()
