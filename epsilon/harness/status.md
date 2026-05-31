# `epsilon.harness` status

## Summary

- Module scope is the merge of upstream `pi-mono/packages/agent` and `pi-mono/packages/coding-agent`: agent runtime + coding-agent harness + built-in tools.
- Agent runtime port is implemented and tested. The module has the core stateful `Agent` wrapper plus low-level loop APIs.
- The local JSON Schema-like validator for tool arguments lives here in `epsilon.harness.validation`.
- Coding-agent harness pieces (built-in tools, system prompt, sessions, config loading, prompt templates, extensions, themes) are not yet implemented and are the next milestone.
- CLI / interactive consumption is intentionally not part of this module. User-facing surfaces live in `epsilon.server` + `epsilon.client` + `epsilon.tui`.

## Implemented

Agent runtime:

- `Agent` wrapper in `epsilon/harness/agent.py`
- low-level loop in `epsilon/harness/agent_loop.py`
- core state, event, tool, and config types in `epsilon/harness/types.py`
- tool argument validation in `epsilon/harness/validation.py`
- package exports in `epsilon/harness/__init__.py`
- parity-focused tests in `tests/harness/test_agent.py` and `tests/harness/test_agent_loop.py`

## Behavior covered now

- `prompt()`
- `continue_()` and `resume()`
- awaited subscriber barrier semantics via `wait_for_idle()`
- sequential and parallel tool execution
- `before_tool_call` and `after_tool_call`
- steering queue
- follow-up queue
- queue clearing helpers
- abort signal plumbing through the runtime and hooks

## Not yet implemented

Next-milestone coding-agent harness scope. Previously tracked under the now-removed `epsilon.coding_agent` module:

- built-in tools: `read`, `write`, `edit`, `bash`, `grep`, `find`, `ls`
- faithful port of the upstream coding-agent system prompt
- session lifecycle (create, resume, fork, dispose, persistence)
- compaction
- config and context file loading: `AGENTS.md`, `CLAUDE.md`, `.pi/SYSTEM.md`
- prompt templates
- skills
- extensions (beyond the existing `convert_to_llm` extension point)
- themes
- faux-provider-driven regression tests for each built-in tool

## Gaps / next work

- add more explicit event-sequence coverage against upstream ordering
- harden/customize custom-message extension guidance beyond `convert_to_llm`
- decide whether the validator should stay harness-local or move into a shared utility layer

## Consumption boundary

- CLI / interactive / wire consumption is owned by `epsilon.server`, `epsilon.client`, and `epsilon.tui`
- the harness exposes programmable primitives; it does not own a CLI
- in-process use of harness primitives is supported for library callers and tests, but is not the supported entry point for the coding agent itself

Out-of-scope note:

- the upstream proxy helper (`proxy.ts`) is intentionally not planned for current epsilon use cases

## Work log

- 2026-04-03: reviewed root docs and repo state before starting the agent port
- 2026-04-03: ported core agent types, event model, low-level loop, stateful `Agent`, queueing, and tool pipeline
- 2026-04-03: added initial agent parity tests and verified them with `pytest tests/agent` (now `tests/harness`)
- 2026-04-03: updated README/module docs/root todo to reflect the implemented surface area
- 2026-04-03: added abort/continue parity coverage plus missing upstream agent-loop and agent wrapper regression tests
- 2026-04-16: synced with upstream pi-mono, ported `after_tool_call` finalization error guard (pi-mono b9cd557d)
- 2026-05-31: renamed `epsilon.agent` to `epsilon.harness` and absorbed the former `epsilon.coding_agent` scope; coding tools, system prompt, sessions, config loading, prompt templates, extensions, and themes are now next-milestone work under the harness rather than a separate module. CLI / interactive consumption moved out of harness scope into `epsilon.server` + `epsilon.client` + `epsilon.tui`.
