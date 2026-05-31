# `epsilon.llm` examples

Runnable. Use the built-in faux provider so they need no API keys.

| File | Shows |
|------|-------|
| `01_minimal_complete.py` | `complete()` against a faux provider |
| `02_streaming.py` | `stream()` event loop covering every `AssistantMessageEvent` variant |
| `03_tools.py` | tool definitions + handling `toolCall` content blocks + tool-result follow-up |
| `04_thinking.py` | reasoning/thinking content blocks |
| `05_cross_provider_handoff.py` | continuing a `Context` against a second provider |
| `06_faux_provider.py` | faux provider as a testing tool, scripted responses |

Switching to a real provider is a one-line change: replace
`registration.get_model()` with `get_model("anthropic", "claude-...")` and set
the appropriate environment variable (e.g. `ANTHROPIC_API_KEY`).

Upstream reference: `pi-mono/packages/ai/README.md` Quick Start and Tools
sections.
