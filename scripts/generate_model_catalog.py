from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

UPSTREAM_MODEL_CATALOG = Path("/Users/ecal/projects/pi-mono/packages/ai/src/models.generated.ts")
DEFAULT_OUTPUT = Path("/Users/ecal/projects/epsilon-ai/epsilon/llm/model_catalog.py")
UPSTREAM_PROVIDERS = (
    "anthropic",
    "azure-openai-responses",
    "openai-codex",
    "openai",
)
PROVIDER_ALIASES: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class CostSpec:
    input: str
    output: str
    cache_read: str
    cache_write: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    name: str
    api: str
    provider: str
    base_url: str
    reasoning: bool
    input_modalities: tuple[str, ...]
    cost: CostSpec
    context_window: str
    max_tokens: str


def _extract_braced_block(text: str, brace_index: int) -> tuple[str, int]:
    if text[brace_index] != "{":
        raise ValueError(f"Expected '{{' at index {brace_index}")

    depth = 0
    in_string = False
    escaped = False

    for index in range(brace_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index : index + 1], index + 1

    raise ValueError("Unterminated braced block")


def _extract_provider_block(source: str, provider: str) -> str:
    marker = f'"{provider}": '
    marker_index = source.find(marker)
    if marker_index < 0:
        raise ValueError(f"Provider {provider!r} not found in upstream catalog")

    brace_index = source.find("{", marker_index + len(marker))
    if brace_index < 0:
        raise ValueError(f"Provider {provider!r} is missing an opening brace")

    block, _ = _extract_braced_block(source, brace_index)
    return block


def _parse_string_field(field: str, body: str) -> str:
    match = re.search(rf"\b{re.escape(field)}:\s*(\"(?:\\.|[^\"])*\")", body)
    if match is None:
        raise ValueError(f"Missing string field {field!r}")
    return json.loads(match.group(1))


def _parse_bool_field(field: str, body: str) -> bool:
    match = re.search(rf"\b{re.escape(field)}:\s*(true|false)", body)
    if match is None:
        raise ValueError(f"Missing bool field {field!r}")
    return match.group(1) == "true"


def _parse_number_field(field: str, body: str) -> str:
    match = re.search(rf"\b{re.escape(field)}:\s*(-?\d+(?:\.\d+)?)", body)
    if match is None:
        raise ValueError(f"Missing numeric field {field!r}")
    return match.group(1)


def _parse_input_modalities(body: str) -> tuple[str, ...]:
    match = re.search(r"\binput:\s*(\[[^\]]*\])", body)
    if match is None:
        raise ValueError("Missing input field")
    return tuple(json.loads(match.group(1)))


def _parse_cost(body: str) -> CostSpec:
    match = re.search(r"\bcost:\s*\{", body)
    if match is None:
        raise ValueError("Missing cost block")

    cost_block, _ = _extract_braced_block(body, match.end() - 1)
    return CostSpec(
        input=_parse_number_field("input", cost_block),
        output=_parse_number_field("output", cost_block),
        cache_read=_parse_number_field("cacheRead", cost_block),
        cache_write=_parse_number_field("cacheWrite", cost_block),
    )


def _parse_model_block(body: str) -> ModelSpec:
    provider = _parse_string_field("provider", body)
    return ModelSpec(
        id=_parse_string_field("id", body),
        name=_parse_string_field("name", body),
        api=_parse_string_field("api", body),
        provider=PROVIDER_ALIASES.get(provider, provider),
        base_url=_parse_string_field("baseUrl", body),
        reasoning=_parse_bool_field("reasoning", body),
        input_modalities=_parse_input_modalities(body),
        cost=_parse_cost(body),
        context_window=_parse_number_field("contextWindow", body),
        max_tokens=_parse_number_field("maxTokens", body),
    )


def _replace_model_provider(
    model: ModelSpec,
    *,
    api: str,
    provider: str,
    base_url: str,
) -> ModelSpec:
    return ModelSpec(
        id=model.id,
        name=model.name,
        api=api,
        provider=provider,
        base_url=base_url,
        reasoning=model.reasoning,
        input_modalities=model.input_modalities,
        cost=model.cost,
        context_window=model.context_window,
        max_tokens=model.max_tokens,
    )


def _parse_provider_models(source: str, provider: str) -> dict[str, ModelSpec]:
    provider_block = _extract_provider_block(source, provider)
    models: dict[str, ModelSpec] = {}
    index = 1

    while True:
        match = re.search(r'\n\s+"([^\"]+)":\s*\{', provider_block[index:])
        if match is None:
            return models

        model_id = match.group(1)
        brace_index = index + match.end() - 1
        body, next_index = _extract_braced_block(provider_block, brace_index)
        models[model_id] = _parse_model_block(body)
        index = next_index


def load_upstream_models(source_path: Path) -> dict[str, dict[str, ModelSpec]]:
    source = source_path.read_text()
    upstream = {
        PROVIDER_ALIASES.get(provider, provider): _parse_provider_models(source, provider)
        for provider in UPSTREAM_PROVIDERS
    }

    foundry_models = {
        model_id: _replace_model_provider(model, api="foundry", provider="foundry", base_url="")
        for model_id, model in upstream["azure-openai-responses"].items()
    }
    foundry_models.update(
        {
            model_id: _replace_model_provider(
                model,
                api="foundry",
                provider="foundry",
                base_url="",
            )
            for model_id, model in upstream["anthropic"].items()
        }
    )

    return {
        "anthropic": upstream["anthropic"],
        "foundry": foundry_models,
        "openai": upstream["openai"],
        "openai-codex": upstream["openai-codex"],
    }


def _render_model(model: ModelSpec) -> str:
    input_modalities = ", ".join(repr(item) for item in model.input_modalities)
    return "\n".join(
        [
            "        Model(",
            f"            id={model.id!r},",
            f"            name={model.name!r},",
            f"            api={model.api!r},",
            f"            provider={model.provider!r},",
            f"            base_url={model.base_url!r},",
            f"            reasoning={model.reasoning!s},",
            f"            input=[{input_modalities}],",
            "            cost=Cost(",
            f"                input={model.cost.input},",
            f"                output={model.cost.output},",
            f"                cache_read={model.cost.cache_read},",
            f"                cache_write={model.cost.cache_write},",
            "            ),",
            f"            context_window={model.context_window},",
            f"            max_tokens={model.max_tokens},",
            "        ),",
        ]
    )


def render_model_catalog(models_by_provider: dict[str, dict[str, ModelSpec]]) -> str:
    lines = [
        "# This file is auto-generated by scripts/generate_model_catalog.py",
        "# Do not edit manually. Run `python scripts/generate_model_catalog.py` to update.",
        "",
        "from __future__ import annotations",
        "",
        "from .types import Cost, Model",
        "",
        "BUILTIN_MODELS: dict[str, dict[str, Model]] = {",
    ]

    for provider in sorted(models_by_provider):
        lines.append(f"    {provider!r}: {{")
        for model_id in sorted(models_by_provider[provider]):
            model = models_by_provider[provider][model_id]
            lines.append(f"        {model_id!r}:")
            lines.append(_render_model(model))
        lines.append("    },")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=UPSTREAM_MODEL_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = render_model_catalog(load_upstream_models(args.source))
    existing = args.output.read_text() if args.output.exists() else None

    if args.check:
        if existing != rendered:
            print(f"{args.output} is out of date", file=sys.stderr)
            return 1
        return 0

    args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
