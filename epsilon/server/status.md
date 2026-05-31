# `epsilon.server` status

## Summary

- Package scaffolding only.
- No transport, no endpoints, no harness wiring yet.

## Planned scope

- Host an `epsilon.harness.Agent` per session.
- Expose endpoints for session lifecycle, prompts, steering, follow-ups,
  abort, event subscription, tool execution control, and config.
- Be the only entry point used by the coding agent CLI/TUI -- there is
  no supported in-process harness API for the coding agent.
- Support both local (loopback / unix socket) and remote transports
  behind the same surface.

## Open design questions

- Transport: HTTP+SSE vs WebSocket vs both.
- Authn/authz model for non-local use.
- Multi-session vs single-session per server process.
- Streaming protocol shape (mirror `epsilon.harness` events).
- Session persistence layer ownership (server vs harness).
