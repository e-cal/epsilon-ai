# epsai

`epsai` is the Python port of `~/projects/pi-mono/`.

## Layout

The repository now ships as one Python distribution with module-level divisions:

- `epsai.llm`
- `epsai.agent`
- `epsai.coding_agent`
- `epsai.tui`

The TypeScript monorepo remains the specification. Port behavior first, then refine architecture.

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
