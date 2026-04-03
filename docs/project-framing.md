# Project framing

This document captures early repository-level decisions for Epsilon AI Framework, the Python port of `pi-mono`.

## Repository layout

The repository uses a single Python distribution with module boundaries that mirror the upstream package split where practical:

- `epsai/llm/` → Python LLM client / provider layer
- `epsai/agent/` → Python agent framework
- `epsai/coding_agent/` → Python coding harness / CLI
- `epsai/tui/` → Python terminal UI support

Tests live under `tests/`, grouped by module.

Python import module names:

- `epsai.llm`
- `epsai.agent`
- `epsai.coding_agent`
- `epsai.tui`

## Tooling

Repository-level tooling decisions:

- dependency management: `uv`
- linting and formatting: `ruff`
- type checking: `pyright` in `standard` mode
- testing: `pytest`
- build backend: `hatchling`

## Porting conventions

### Naming conventions

- Mirror upstream package and module boundaries where practical so Python and TypeScript remain easy to compare.
- Python modules and files use `snake_case`.
- Python classes use `PascalCase`.
- Python functions, methods, and variables use `snake_case`.
- Preserve upstream concept names and event type strings where they are user-visible or semantically important.
- When an upstream file name contains `-`, convert it to `_` in Python.
- Prefer Pythonic public function names first. Add parity aliases later only when compatibility or migration needs justify them.

### Async and event-stream conventions

- Represent streaming APIs with `AsyncIterator`-based event streams.
- Keep the upstream event ordering and event type vocabulary wherever practical.
- Use small typed event objects rather than untyped dicts for internal code.
- Keep stream events append-only from the consumer perspective: later events may complete or refine prior partial state, but should not mutate past emitted events.
- Separate stream transport concerns from higher-level agent/session state.
- Prefer explicit cancellation plumbing over hidden globals or implicit task cancellation.

### Schema and validation strategy

This remains the main open framing decision.

Current recommendation:

- use plain Python dataclasses for internal state/models
- use JSON Schema-compatible `dict` definitions for tool/input schemas when parity with upstream matters
- use a lightweight runtime validator rather than a model framework as the primary abstraction

Open question: choose the primary runtime validation layer for schemas and tool arguments.
