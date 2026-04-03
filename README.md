# Epsilon

Python port of `~/projects/pi-mono/`.

## Scope

Current target packages:

- `packages/ai`
- `packages/agent`
- `packages/coding-agent`
- `packages/tui`

The TypeScript monorepo remains the specification. Port behavior first, then refine architecture.

See `docs/project-framing.md` for current repository layout and porting conventions.

## Tooling

This repo uses:

- `uv` for workspace, dependency management, and command execution
- `ruff` for linting and formatting
- `pyright` for type checking
- `pytest` for tests

## Workspace commands

With `direnv` enabled, this repo uses the `epsilon/` virtual environment automatically.

```bash
uv sync --all-packages
ruff check .
ruff format .
pyright
pytest
```
