# `epsilon.client` status

## Summary

- Package scaffolding only.
- No transport, no API surface yet.

## Planned scope

- Provide an async Python client for every `epsilon.server` endpoint.
- Be the only sanctioned consumer surface for `epsilon.tui` and for
  external Python integrations of the coding agent.
- Mirror the server's streaming/event model rather than re-implement
  the harness loop locally.

## Open design questions

- Sync wrappers around async API.
- Reconnection / replay semantics for in-flight sessions.
- Whether the client owns the embedded local server process when
  running in standalone mode, or whether a separate launcher does.
