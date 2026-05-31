# Sketch: wire protocol walkthrough

Status: **design sketch**. Transport choice is still open
(HTTP + SSE leading). Names below are proposals.

## Goal

Show one end-to-end interaction over the wire so the
`epsilon.server` ↔ `epsilon.client` contract is concrete.

## Session lifecycle

```
POST /v1/sessions
    body: { cwd, model, thinking_level, tools, system_prompt_override?, ... }
    response: { session_id: "sess_abc" }

POST /v1/sessions/sess_abc/prompt
    body: { input: "List files in this repo." }
    response: 202 Accepted, body: { run_id: "run_001" }

GET  /v1/sessions/sess_abc/events?from=0
    Server-Sent Events stream of AgentEvent

POST /v1/sessions/sess_abc/abort
POST /v1/sessions/sess_abc/steer        body: AgentMessage
POST /v1/sessions/sess_abc/follow_up    body: AgentMessage
DELETE /v1/sessions/sess_abc
```

`session_id` is opaque. `run_id` identifies a single `prompt()` /
`continue_()` / `steer()` invocation; events carry `run_id` so the client
can correlate.

## Event stream framing

Each SSE `data:` line is a JSON-encoded `AgentEvent`. Field names match the
Python dataclasses in `epsilon.harness.types` 1:1, with snake_case
preserved.

```
event: agent_event
data: {"type":"agent_start","run_id":"run_001"}

event: agent_event
data: {"type":"turn_start","run_id":"run_001"}

event: agent_event
data: {"type":"message_start","run_id":"run_001","message":{"role":"user","content":"List files in this repo."}}

event: agent_event
data: {"type":"message_start","run_id":"run_001","message":{"role":"assistant","content":[]}}

event: agent_event
data: {"type":"message_update","run_id":"run_001","assistant_message_event":{"type":"text_delta","content_index":0,"delta":"I'll "}}

event: agent_event
data: {"type":"message_update","run_id":"run_001","assistant_message_event":{"type":"text_delta","content_index":0,"delta":"list "}}

event: agent_event
data: {"type":"tool_execution_start","run_id":"run_001","tool_call_id":"tc_1","tool_name":"ls","args":{"path":"."}}

event: agent_event
data: {"type":"tool_execution_end","run_id":"run_001","tool_call_id":"tc_1","tool_name":"ls","result":{...},"is_error":false}

event: agent_event
data: {"type":"turn_end","run_id":"run_001","message":{...},"tool_results":[{...}]}

event: agent_event
data: {"type":"agent_end","run_id":"run_001","messages":[...]}
```

Event ordering must match `epsilon.harness`. The server is a transport
over the harness, not a re-implementation.

## Reconnect semantics

`GET /v1/sessions/{id}/events?from=<seq>` replays events from the given
sequence number. The server retains the last N events per session for
reconnect; older events are dropped. If the client requests a `from` that
has been evicted, the server responds with the current state snapshot plus
a `gap` event so the client can resync.

## Tool execution hooks over the wire

Before/after-tool hooks are server-owned by default (they run in the same
process as the harness). Client-owned hooks (e.g. an interactive permission
prompt in the TUI) use a separate channel:

```
POST /v1/sessions/{id}/tool_hooks/subscribe
    SSE stream of:
        { type: "before_tool_call", call_id, tool_name, args }
        { type: "after_tool_call",  call_id, tool_name, result, is_error }

POST /v1/sessions/{id}/tool_hooks/respond
    body: { call_id, decision: "allow" | "deny", reason? }
```

Hook responses must arrive before the server proceeds; if no client is
subscribed, the default policy (configured at session create) applies.

## Open questions

- whether to use WebSocket instead of HTTP + SSE for bidirectional control
  (steer, hook responses); current preference is SSE + plain POST for
  simplicity
- backpressure: SSE has none; if the client lags, do we drop, buffer, or
  block the harness? Likely buffer with a high-water mark, then surface a
  `client_lag` event
- session export format: JSON-lines event log vs structured snapshot;
  needed for session resume across restarts
