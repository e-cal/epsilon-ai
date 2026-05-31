# `epsilon.client` examples

Status: **not yet built**. Module is scaffolding only.

These are **work-backward design sketches** modeled on
`pi-mono/packages/coding-agent/examples/sdk/`. They show the shape the
Python client should expose to consumers (notably `epsilon.tui` and
external Python integrations of the coding agent).

| File | Mirrors | Shows |
|------|---------|-------|
| `01_minimal.md` | sdk/01-minimal.ts | simplest usage, all defaults |
| `02_custom_model.md` | sdk/02-custom-model.ts | model + thinking level |
| `03_custom_prompt.md` | sdk/03-custom-prompt.ts | system prompt overrides |
| `04_tools.md` | sdk/05-tools.ts | built-in tool allowlist, custom tools |
| `05_sessions.md` | sdk/11-sessions.ts | in-memory, persistent, resume, list |
| `06_full_control.md` | sdk/12-full-control.ts | replace everything, no discovery |

## Architectural note vs upstream

`pi-mono/packages/coding-agent` is consumed in-process via
`createAgentSession()`. epsilon is **server-first**: even standalone
single-user invocations spin up a local `epsilon.server` (see
`examples/server/01_launch_local_server.md`) and `epsilon.client` is the
canonical consumer. Each example below is therefore phrased as

```
client = await Client.connect(...)        # or Client.standalone(...)
session = await client.create_session(...)
```

instead of upstream's

```
const { session } = await createAgentSession({ ... });
```

The configuration surface (model, thinking_level, tools, prompt overrides,
context files, extensions, session manager, settings) mirrors upstream;
only the consumption shape changes. The `Client.standalone()` constructor
owns an embedded local `Server` so the standalone case is a one-liner.

## Open design questions

- `Client.standalone()` ownership: client spawns + manages the embedded
  `Server`, or a separate launcher does. Leaning toward client-managed
  for ergonomic standalone use.
- sync wrapper: provide `Client.sync` blocking helpers via `asyncio.run`,
  or a separate `epsilon.client.sync` module. TBD.
- reconnection: transparent resume vs surfaced gap events. Default likely
  transparent for embedded mode, configurable for hosted mode.
- extension surface: the `pi-mono` extensions system is largely TUI- and
  config-driven; in epsilon the extension surface lives between
  client/server. Exact split is TBD.
