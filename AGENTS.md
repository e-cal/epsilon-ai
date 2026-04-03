# Development Rules

This repository is an early-stage Python port of `~/projects/pi-mono/`.

Primary goal: achieve 1:1 feature and behavior parity with the TypeScript monorepo while keeping the Python codebase clean, explicit, and readable.

Primary target scope for the port:
- `epsai.llm` -> Python LLM client / provider layer
- `epsai.agent` -> Python agent framework
- `epsai.coding_agent` -> Python coding agent harness / CLI
- `epsai.tui` -> Python terminal UI support needed by the coding agent

Out of scope for now unless the user explicitly asks:
- `packages/mom`
- `packages/pods`
- `packages/web-ui`

The TypeScript source repo is the specification. When behavior is unclear, read `~/projects/pi-mono/` and port the original behavior rather than inventing a new design. Try to maintain similar code structures and style along with behavior.

## First Message
If the user did not give a concrete task in their first message:
1. Read `README.md`
2. Ask which module to work on
3. Read the relevant local module docs and source material in `~/projects/pi-mono/` before changing Python code

When starting work on a subsystem, prioritize reading:
- `README.md`
- `docs/modules/llm.md`
- `docs/modules/agent.md`
- `docs/modules/coding_agent.md`
- `docs/modules/tui.md` when the work touches terminal UI

Relevant upstream docs:
- `pi-mono/packages/ai/README.md`
- `pi-mono/packages/agent/README.md`
- `pi-mono/packages/coding-agent/README.md`
- `pi-mono/packages/tui/README.md` when the work touches terminal UI

## Core Porting Rules
- Preserve user-visible behavior from `pi-mono` unless the user asks otherwise
- Prefer structural parity with the original repo so the Python port remains easy to compare against upstream
- Keep a clear separation between:
  - AI/provider router
  - agent runtime
  - coding agent harness
  - TUI support code
- TUI is an explicit area where implementation may intentionally diverge from upstream
  - We still want equivalent end-user capabilities in the coding agent
  - Language/framework parity is not required for the TUI layer
  - Modularity and hackability matter more than strict upstream structural matching here
  - TUI work is planned for later, after the core AI/agent/harness layers are established
- Omit non-essential features until requested, but do not accidentally design the architecture so they become impossible to add later
- When behavior differs between a "Pythonic" rewrite and the original implementation, prefer parity first, then refactor carefully
- Do not remove functionality that exists upstream without asking
- Do not preserve backward compatibility unless the user explicitly asks for it

## Python Code Quality
- Use Python 3.12+ features where they improve clarity
- Prefer standard library types, `dataclass`es, and well-typed interfaces
- Add type hints everywhere practical
- Prefer explicit modules and top-level imports; avoid lazy/dynamic imports unless there is a strong reason
- Keep functions and classes small and legible
- Use `pathlib` instead of raw string path manipulation where practical
- Prefer pure functions and explicit state transitions in core runtime code
- Match upstream event/state semantics closely, especially in streaming, tools, and sessions
- For TUI code, prefer a modular, hackable design over strict implementation parity; preserve important user-facing workflows where practical
- Use Python naming conventions by default: modules/functions/variables in `snake_case`, classes in `PascalCase`
- Preserve upstream concept names and event type strings where they are user-visible or semantically important
- When porting upstream file names with `-`, convert them to `_` in Python
- Prefer `AsyncIterator`-based event streams for streaming APIs and keep event ordering close to upstream

## Project Structure
The Python port ships as a single distribution with module-level boundaries:
- `epsai/llm/`
- `epsai/agent/`
- `epsai/coding_agent/`
- `epsai/tui/`
- `tests/llm/`

Python import module names:
- `epsai.llm`
- `epsai.agent`
- `epsai.coding_agent`
- `epsai.tui`

Layout preference:
- Keep Python code inside `epsai/`
- Keep tests inside `tests/`
- Avoid JS-style `src/` nesting unless there is a clear Python-specific reason and the user agrees

If the repo has not reached the full upstream structure yet, create code with that destination in mind.

TUI note:
- The TUI module may ultimately be implemented with a different stack than upstream
- Candidate directions currently include:
  - follow `pi` closely
  - custom Python TUI using Textual
  - follow `~/projects/opencode` using OpenTUI patterns
  - custom OpenTUI-based implementation
- Current preference is an OpenTUI-based, opencode-inspired hybrid
- Treat this as a late-phase design area; optimize for modularity and experimentation

## Commands
Use Python-equivalent commands that fit the repository as it exists.

Preferred tooling once available:
- package management: `uv` only (never `pip`)
- format/lint: `ruff check`, `ruff format`
- type checking: `pyright`
- tests: `pytest`

Rules:
- After code changes, run the relevant Python checks for the files/modules changed
- If you create or modify tests, run those tests and iterate until they pass
- Use `uv` for installs and lockfile updates
- The repo virtual environment lives in `.venv/`; with `direnv` allowed, bare commands like `ruff`, `pyright`, and `pytest` should work
- Prefer `pyright` in `standard` mode unless the user asks for stricter or looser settings
- Do not run unrelated long-running commands unless the user asks
- Never commit unless the user asks

## Testing Guidance
- Prefer deterministic unit tests around provider normalization, event streams, tool execution, session handling, and TUI state transitions
- For coding-agent integration tests, prefer faux/fake providers over real provider APIs
- Do not require paid tokens or live API keys in tests
- When porting behavior, add regression tests for subtle upstream semantics

## AI Provider Scope (current)
For the initial `epsai.llm` port, prioritize only:
- OpenAI via the Responses API
- Anthropic Messages API
- Azure OpenAI Responses API

Notes:
- Do not spend time on OpenAI Chat Completions or secondary providers unless the user asks
- Azure largely shares response semantics with OpenAI Responses, but still has separate auth/base URL/api-version/deployment handling

## Source of Truth
When implementing a feature, inspect the corresponding TypeScript source in `~/projects/pi-mono/`, not just the README docs.

Examples:
- provider behavior: `pi-mono/packages/ai/src/`
- agent loop/runtime behavior: `pi-mono/packages/agent/src/`
- coding harness and CLI behavior: `pi-mono/packages/coding-agent/src/`
- TUI behavior: `pi-mono/packages/tui/src/`

Read the original files fully before porting or changing the Python equivalent.

## Style
- Keep responses short and technical
- No fluff
- No emojis in code, commits, or docs

## Tool Usage Rules
- Use the `read` tool to inspect files
- Use `bash` for discovery commands like `find`, `rg`, and `ls`
- You must read every file you modify in full before editing
- Always look for a `continue.md` file in the relevant module/directory before starting or resuming work
- If `continue.md` exists, read it first; after reading it, it may be deleted
- Only create a `continue.md` file when the user explicitly asks for it
- When creating `continue.md`, record:
  - what was just finished
  - what is currently in progress
  - immediate next todos
  - enough concrete code snippets, file paths, command references, and implementation notes that another agent can continue immediately without re-discovery

## Git Rules for Parallel Agents
Multiple agents may work in the same tree.

- Only commit files you changed in this session
- Never use `git add -A` or `git add .`
- Before committing, check `git status`
- Never use destructive commands like `git reset --hard`, `git checkout .`, or `git clean -fd`
- Never force push

## Working Principle
Port behavior first.
Refine architecture second.
Keep the Python code readable throughout.

## Maintenance
- Keep this file up to date as tooling decisions, code structure decisions, or workflow guidance change
