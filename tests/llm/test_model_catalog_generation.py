from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from epsilon.llm import get_model, get_models

ROOT = Path(__file__).resolve().parents[2]


def test_generated_model_catalog_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_model_catalog.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_generated_catalog_exposes_recent_upstream_models() -> None:
    openai_ids = {model.id for model in get_models("openai")}
    openai_codex_ids = {model.id for model in get_models("openai-codex")}
    anthropic_ids = {model.id for model in get_models("anthropic")}
    azure_ids = {model.id for model in get_models("azure-openai-responses")}

    assert "gpt-5.4" in openai_ids
    assert "gpt-5.4-mini" in openai_ids
    assert "gpt-5.4" in openai_codex_ids
    assert "claude-opus-4-6" in anthropic_ids
    assert "gpt-5.1-codex-mini" in azure_ids

    model = get_model("openai", "gpt-5.3-codex-spark")
    assert model.max_tokens == 32000
    assert model.input == ["text", "image"]

    codex_model = get_model("openai-codex", "gpt-5.3-codex")
    assert codex_model.base_url == "https://chatgpt.com/backend-api"
