from __future__ import annotations

import os

from .types import Provider


def get_env_api_key(provider: Provider) -> str | None:
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")

    if provider == "foundry":
        return os.environ.get("FOUNDRY_API_KEY")

    if provider == "azure-openai-responses":
        return os.environ.get("AZURE_OPENAI_API_KEY")

    env_map = {
        "openai": "OPENAI_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var is None:
        return None
    return os.environ.get(env_var)
