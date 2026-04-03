# e-ai

Initial Epsilon port of the `pi-mono` AI package.

Current scope:

- shared AI/message/types layer
- model and API registries
- unified `stream()` / `complete()` entry points
- deterministic faux provider for tests
- first-cut real provider support for:
  - OpenAI via the Responses API
  - Anthropic Messages API
  - Azure OpenAI Responses API

Notes:

- Azure is not fully separate in behavior from OpenAI Responses; most response semantics are shared.
- Azure still needs its own auth, base URL, API version, and deployment-name handling, so it remains a separate thin provider layer.
- The current real-provider implementation is an initial non-streaming HTTP pass that normalizes final responses into the shared event protocol.
- True upstream-style incremental streaming parity still needs follow-up work.
- Package layout uses the Python package directly at `packages/ai/e_ai/`; avoid a JS-style `src/` nesting here unless explicitly needed.
