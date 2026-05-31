# `epsilon.harness` examples

Runnable. Cover the **agent runtime primitives**: state, subscribe,
streaming events, tool execution, steering/follow-up queues, abort, and
`continue_()`.

| File | Shows |
|------|-------|
| `01_minimal_agent.py` | `Agent` + faux provider, single prompt |
| `02_streaming_events.py` | full `subscribe()` event walkthrough |
| `03_custom_tool.py` | `AgentTool` calling a local Python function |
| `04_steering_and_followup.py` | `steer()` and `follow_up()` during a run |
| `05_abort_and_continue.py` | `abort()` mid-stream, then `continue_()` to retry |

These exercise the runtime that `epsilon.server` will host. The canonical
end-user path for the coding agent is server-first
(`epsilon.client` → `epsilon.server` → harness runtime), not direct harness
use; see `examples/client/` and `examples/standalone/`.

Upstream reference: `pi-mono/packages/agent/README.md`.

## Not covered yet

Coding tools, system prompt assembly, sessions, prompt templates,
extensions, and config loading are not yet implemented in `epsilon.harness`.
When ported, they will appear as examples in this directory and as the
coding-agent flow in `examples/client/` (server-first consumption).
