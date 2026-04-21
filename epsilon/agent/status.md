# `epsilon.agent` status

## Summary

- Initial runtime port is implemented and tested.
- The module now has the core stateful `Agent` wrapper plus low-level loop APIs.
- The first local JSON Schema-like validator for tool arguments lives here in `epsilon.agent.validation`.

## Implemented

- `Agent` wrapper in `epsilon/agent/agent.py`
- low-level loop in `epsilon/agent/agent_loop.py`
- core state, event, tool, and config types in `epsilon/agent/types.py`
- tool argument validation in `epsilon/agent/validation.py`
- package exports in `epsilon/agent/__init__.py`
- parity-focused tests in `tests/agent/test_agent.py` and `tests/agent/test_agent_loop.py`

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

## Gaps / next work

- add more explicit event-sequence coverage against upstream ordering
- harden/customize custom-message extension guidance beyond `convert_to_llm`
- decide whether the validator should stay agent-local or move into a shared utility layer

Out-of-scope note:

- the upstream proxy helper (`proxy.ts`) is intentionally not planned for current epsilon use cases

## Work log

- 2026-04-03: reviewed root docs and repo state before starting the agent port
- 2026-04-03: ported core agent types, event model, low-level loop, stateful `Agent`, queueing, and tool pipeline
- 2026-04-03: added initial agent parity tests and verified them with `pytest tests/agent`
- 2026-04-03: updated README/module docs/root todo to reflect the implemented surface area
- 2026-04-03: added abort/continue parity coverage plus missing upstream agent-loop and agent wrapper regression tests
- 2026-04-16: synced with upstream pi-mono, ported `after_tool_call` finalization error guard (pi-mono b9cd557d)
