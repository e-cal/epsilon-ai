# `epsilon.agent`

Epsilon AI Framework module corresponding to the upstream `pi-mono/packages/agent` package.

Current implementation:

- `Agent` state wrapper with `prompt()`, `continue_()`, `resume()`, `abort()`, and `wait_for_idle()`
- low-level `agent_loop()` and `agent_loop_continue()` APIs
- agent lifecycle/message/tool execution events with upstream event type strings preserved
- sequential and parallel tool execution modes
- tool argument validation from JSON Schema-like `dict` definitions
- `before_tool_call` and `after_tool_call` hooks
- steering and follow-up queues plus queue clearing helpers

Python-specific note:

- upstream `continue()` is exposed as `continue_()` because `continue` is a Python keyword

Recent upstream parity sync:

- `after_tool_call` hook errors during tool-call finalization are now converted into error tool results instead of aborting the batch (pi-mono b9cd557d)

Not yet ported:

- broader parity and regression coverage from the upstream agent package
- package-level docs for custom message extension strategy beyond `convert_to_llm`

Upstream parity note:

- the upstream `proxy.ts` helper is intentionally out of scope for current epsilon use cases
