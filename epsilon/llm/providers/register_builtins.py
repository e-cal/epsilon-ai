from __future__ import annotations

from typing import cast

from ..api_registry import ApiProvider, clear_api_providers, register_api_provider
from .anthropic import AnthropicOptions, stream_anthropic
from .foundry import FoundryOptions, stream_foundry
from .openai_codex_responses import (
    OpenAICodexResponsesOptions,
    stream_openai_codex_responses,
)
from .openai_responses import (
    OpenAIResponsesOptions,
    stream_openai_responses,
)


def register_built_in_api_providers() -> None:
    register_api_provider(
        ApiProvider(
            api="anthropic-messages",
            stream=lambda model, context, options=None: stream_anthropic(
                model,
                context,
                cast(AnthropicOptions | None, options),
            ),
        )
    )
    register_api_provider(
        ApiProvider(
            api="openai-responses",
            stream=lambda model, context, options=None: stream_openai_responses(
                model,
                context,
                cast(OpenAIResponsesOptions | None, options),
            ),
        )
    )
    register_api_provider(
        ApiProvider(
            api="foundry",
            stream=lambda model, context, options=None: stream_foundry(
                model,
                context,
                cast(FoundryOptions | None, options),
            ),
        )
    )
    register_api_provider(
        ApiProvider(
            api="openai-codex-responses",
            stream=lambda model, context, options=None: stream_openai_codex_responses(
                model,
                context,
                cast(OpenAICodexResponsesOptions | None, options),
            ),
        )
    )


def reset_api_providers() -> None:
    clear_api_providers()
    register_built_in_api_providers()


register_built_in_api_providers()
