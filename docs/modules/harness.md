# `epsilon.harness`

Agent runtime, coding-agent harness, and built-in tools, merged into one module.

This corresponds to the merge of upstream `pi-mono/packages/agent` and `pi-mono/packages/coding-agent` into a single Python module.

## Intended Deviations

- Structural merge: upstream ships `agent` and `coding-agent` as separate packages. The Python port collapses them into `epsilon.harness`. The agent runtime was only ever re-exported and wrapped by the coding-agent layer; keeping them split would force every coding-agent primitive to be re-exposed at one layer up for no behavior gain. The merge keeps the agent runtime and the coding-agent harness in one place.
- `continue` is exposed as `continue_()` because `continue` is a Python keyword.
- The agent uses `epsilon.llm.stream()` directly; there is no separate internal `stream_simple()` path in the Python port.
- Coding tools, the coding-agent system prompt, sessions, config loading, and prompt templates live here rather than in a separate `coding_agent` package.
- CLI / interactive consumption is not part of this module. The harness exposes programmable primitives; user-facing surfaces are the responsibility of `epsilon.server` + `epsilon.client` + `epsilon.tui`. See `docs/modules/server.md`.

These are intentional API and structural adaptations, not missing parity work.

## Implemented

Agent runtime, ported from upstream `pi-mono/packages/agent`:

- `Agent` state wrapper with `prompt()`, `continue_()`, `resume()`, `abort()`, and `wait_for_idle()`
- low-level `agent_loop()` and `agent_loop_continue()` APIs
- agent lifecycle, message, and tool execution events with upstream event type strings preserved
- sequential and parallel tool execution modes
- tool argument validation from JSON Schema-like `dict` definitions
- `before_tool_call` and `after_tool_call` hooks
- steering and follow-up queues plus queue clearing helpers
- abort signal plumbing through the runtime and hooks

Recent upstream parity sync:

- `after_tool_call` hook errors during tool-call finalization are converted into error tool results instead of aborting the batch (pi-mono b9cd557d)

Out of scope for current epsilon use cases:

- the upstream `proxy.ts` helper

## Not yet implemented

These were previously scoped to a separate `coding_agent` module and are now part of the harness scope. They are the next milestone after the runtime parity work:

- built-in tools: `read`, `write`, `edit`, `bash`, `grep`, `find`, `ls`
  - each tool gets a JSON-Schema-like `parameters` dict and an async `execute` function using the existing tool interface
- faithful port of the upstream coding-agent system prompt
- session lifecycle (create, resume, fork, dispose, persistence)
- config and context file loading: `AGENTS.md`, `CLAUDE.md`, `.pi/SYSTEM.md`
- compaction
- prompt templates
- skills
- extensions (beyond the existing `convert_to_llm` extension point)
- themes
- faux-provider-driven regression tests for the harness and each built-in tool

Anything user-facing (CLI, interactive, JSON, RPC) is intentionally not in this module. It is owned by `epsilon.server`, `epsilon.client`, and `epsilon.tui`.

## Consumption

The harness is not intended to be consumed in-process by the coding-agent CLI or by external Python integrations. The sanctioned consumption path is:

- `epsilon.server` hosts an `epsilon.harness.Agent` runtime and exposes it as a wire API
- `epsilon.client` and `epsilon.tui` (and external Python callers) talk to `epsilon.server`

See `docs/modules/server.md` and `docs/modules/client.md`.

In-process use of the agent primitives directly from `epsilon.harness` is supported for library callers and tests, but is not the supported entry point for the coding agent itself.

## Open questions

- broader parity and regression coverage from the upstream agent and coding-agent packages
- explicit event-sequence coverage against upstream ordering
- whether the local JSON Schema-like validator should stay harness-local or move into a shared utility layer
- package-level guidance for custom message extension strategy beyond `convert_to_llm`
