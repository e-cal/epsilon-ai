# epsilon-ai

`epsilon-ai` is the Python port of `~/projects/pi-mono/`.

PyPI distribution: `epsilon-ai`
Python package/imports: `epsilon`

## Current status

- `epsilon.llm`: provider/router port is implemented for OpenAI Responses, OpenAI Codex Responses, Foundry, Anthropic Messages, and the faux test provider. OAuth is ported for OpenAI Codex only. Parity sync against upstream includes Opus 4.7 adaptive thinking, `thinking_display`, separated tool cache control, OpenAI-compatible session cache headers, and Codex service tier handling.
- `epsilon.agent`: runtime port is implemented with state, events, low-level loop APIs, tool execution, steering/follow-up queues, the stateful `Agent` wrapper, and guarded `after_tool_call` hook error handling in finalization.
- `epsilon.coding_agent`: package scaffolding only. This is the next milestone.
- `epsilon.tui`: package scaffolding only. Intentionally deferred until after the coding agent harness is usable end-to-end.

## Layout

The repository ships as one Python distribution with module-level divisions:

- `epsilon.llm`
- `epsilon.agent`
- `epsilon.coding_agent`
- `epsilon.tui`

The TypeScript monorepo is the specification. Port behavior first, then refine architecture.

See `docs/project-framing.md` for repository-level conventions.

Module docs:

- `docs/modules/llm.md`
- `docs/modules/agent.md`
- `docs/modules/coding_agent.md`
- `docs/modules/tui.md`

## Tooling

This repo uses:

- `uv` for dependency management and command execution
- `ruff` for linting and formatting
- `pyright` for type checking
- `pytest` for tests

## Commands

With `direnv` enabled, this repo uses the `.venv/` environment automatically.

```bash
uv sync
ruff check .
ruff format .
pyright
pytest
```
