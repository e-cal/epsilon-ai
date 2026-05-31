# `epsilon.tui` examples

Status: **deferred**. Module is scaffolding only; no examples yet.

## Why no examples yet

The TUI sits at the top of the stack and depends on `epsilon.client`, which
depends on `epsilon.server`. None of those have a stable surface yet. Writing
TUI examples now would lock in a consumption shape before the underlying
client API is settled.

TUI work is planned for after `epsilon.server`, `epsilon.client`, and the
coding-tool / system-prompt / session pieces of `epsilon.harness` are usable
end-to-end. See `docs/modules/tui.md`.

## Architectural direction

Intentional deviation from `pi-mono/packages/tui`:

- OpenTUI-based, modeled on `~/projects/opencode`'s TUI architecture
- modularity and hackability prioritized over upstream component parity
- equivalent end-user capability is the bar, not 1:1 structural match

## Consumption boundary

`epsilon.tui` consumes `epsilon.client`. It does **not** talk to
`epsilon.harness` directly, and it does **not** embed `epsilon.server`.
Standalone-mode server lifecycle is owned by the client layer (or a
dedicated launcher); the TUI only ever sees the client API.

In sketch form:

```
epsilon.tui  ──►  epsilon.client  ──(wire)──►  epsilon.server  ──►  epsilon.harness
```

There is no shortcut. Even the standalone single-process invocation goes
through the wire, exactly like a hosted deployment. See
`examples/standalone/` for what that looks like end-to-end.

## What concrete TUI examples will eventually cover

Once the client surface stabilizes, this directory will likely host
runnable examples for:

- minimal interactive loop driving a single session through the client
- streaming assistant output and tool calls into TUI components
- keybindings, theme, and component composition
- session list / resume picker
- model selection and reasoning-level UI
- extension surface (the split between client- and TUI-side extension code
  is itself one of the open questions in `docs/modules/client.md`)

Until those land, the design notes in `docs/modules/tui.md` and the
client-side sketches in `examples/client/` are the canonical reference.

## Reference

- `docs/modules/tui.md` — module scope and direction
- `~/projects/opencode/` — primary architectural model
- `pi-mono/packages/tui/` — reference only; structural parity is **not** a
  goal here
