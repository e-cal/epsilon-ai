# epsilon-ai

`epsilon-ai` is the Python port of `~/projects/pi-mono/`.

PyPI distribution: `epsilon-ai`
Python package/imports: `epsilon`

## Current status

- `epsilon.llm`: provider/router port is implemented for OpenAI Responses, OpenAI Codex Responses, Foundry, Anthropic Messages, and the faux test provider. OAuth is ported for OpenAI Codex only. Parity sync against upstream includes Opus 4.7 adaptive thinking, `thinking_display`, separated tool cache control, OpenAI-compatible session cache headers, and Codex service tier handling.
- `epsilon.harness`: agent runtime is implemented (state, events, low-level loop APIs, tool execution, steering/follow-up queues, the stateful `Agent` wrapper, guarded `after_tool_call` hook error handling). Coding tools, system prompt loading, sessions, and config loading are not yet implemented.
- `epsilon.server`: package scaffolding only.
- `epsilon.client`: package scaffolding only.
- `epsilon.tui`: package scaffolding only. Intentionally deferred until after the server/client surface is usable end to end.

### Intended deviations from pi-mono

Upstream `agent` and `coding-agent` are merged into a single `epsilon.harness` module. Coding-agent functionality is server-first only: even standalone single-user invocations run through `epsilon.server` — there is no in-process coding-agent API. `epsilon.tui` is OpenTUI-based and modeled on `~/projects/opencode`, not on `pi-mono/packages/tui`.

## Layout

The repository ships as one Python distribution with module-level divisions:

- `epsilon.llm`
- `epsilon.harness`
- `epsilon.server`
- `epsilon.client`
- `epsilon.tui`

The TypeScript monorepo is the specification. Port behavior first, then refine architecture.

See `docs/project-framing.md` for repository-level conventions.

Module docs:

- `docs/modules/llm.md`
- `docs/modules/harness.md`
- `docs/modules/server.md`
- `docs/modules/client.md`
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
