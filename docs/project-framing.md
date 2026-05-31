# Project framing

This document captures early repository-level decisions for Epsilon AI Framework, the Python port of `pi-mono`.

## Repository layout

The repository uses a single Python distribution with module boundaries that mirror the upstream package split where practical, with documented deliberate deviations:

- `epsilon/llm/` → Python LLM client / provider layer
- `epsilon/harness/` → agent runtime + coding-agent harness + built-in tools
- `epsilon/server/` → server hosting an `epsilon.harness` runtime (no upstream equivalent)
- `epsilon/client/` → Python client for `epsilon.server` (no upstream equivalent)
- `epsilon/tui/` → Python terminal UI (OpenTUI-based)

Tests live under `tests/`, grouped by module.

Python import module names:

- `epsilon.llm`
- `epsilon.harness`
- `epsilon.server`
- `epsilon.client`
- `epsilon.tui`

## Intended deviations from upstream

- Upstream `pi-mono/packages/agent` and `pi-mono/packages/coding-agent` are merged into a single `epsilon.harness` module.
- The coding agent is server-first: `epsilon.server` is mandatory for all coding-agent usage, including standalone single-user invocations. There is no in-process coding-agent path; `epsilon.client` is the canonical consumption surface.
- `epsilon.tui` is OpenTUI-based, modeled on `~/projects/opencode`, rather than tracking `pi-mono/packages/tui`.

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

Current baseline:

- use plain Python dataclasses for internal state/models
- use JSON Schema-compatible `dict` definitions for tool/input schemas when parity with upstream matters
- use a lightweight runtime validator rather than a model framework as the primary abstraction
- `epsilon.harness.validation` now provides the first concrete implementation of that approach for tool-argument validation

Open follow-up: decide when to extract that validator into a shared cross-module utility instead of keeping it local to `epsilon.harness`.
