# Examples

Usage examples for `epsilon-ai`.

These examples mirror the structure of `pi-mono`'s docs and the
`pi-mono/packages/coding-agent/examples/sdk/` numbered SDK examples, adapted
to the Python port. They are the working specification for the Python API.

## Module status

| Module | Status | Examples format |
|--------|--------|-----------------|
| `epsilon.llm` | implemented | runnable `.py` |
| `epsilon.harness` | runtime implemented; coding tools and config loading pending | runnable `.py` |
| `epsilon.server` | scaffolding only | design sketches in `.md` |
| `epsilon.client` | scaffolding only | design sketches in `.md` |
| `epsilon.tui` | scaffolding only, deferred | design notes only |

The runnable examples use the built-in faux provider (`register_faux_provider`)
so they do not require API keys and produce deterministic output. Real
provider usage is identical apart from the model lookup; switch
`registration.get_model()` for `get_model("anthropic", "claude-sonnet-4-...")`
or `get_model("openai", "gpt-5-...")`.

## Layout

```
examples/
  llm/         runnable provider router examples
  harness/     runnable agent runtime examples
  server/      work-backward design sketches for the wire API
  client/      work-backward design sketches for the canonical client
  tui/         design notes (intentional deviation, OpenTUI-based)
  standalone/  work-backward sketch of the server-first standalone agent
```

## Running runnable examples

```bash
uv sync
uv run python examples/llm/01_minimal_complete.py
uv run python examples/harness/01_minimal_agent.py
```

With `direnv` enabled the `uv run` prefix is optional:

```bash
python examples/llm/02_streaming.py
```

## Architectural note

The coding-agent in epsilon is **server-first**: there is no in-process
coding-agent Python API. Even standalone single-user invocations run through
`epsilon.server`, consumed by `epsilon.client`. This deviates from
`pi-mono/packages/coding-agent`, which is consumed in-process via
`createAgentSession()`.

That means the examples for the coding-agent flow live under `client/` and
`standalone/`, not under `harness/`. `harness/` examples cover the
**agent runtime primitives** that the server hosts — useful for tests and for
building alternative consumers of the runtime, but not the canonical path for
running the coding agent.

## Source-of-truth reference

When porting a behavior, the TypeScript implementation in
`~/projects/pi-mono/packages/{ai,agent,coding-agent}/src/` is the
specification. The `client/` and `standalone/` sketches are intentional
deviations from upstream's in-process model and have no direct upstream
counterpart.
