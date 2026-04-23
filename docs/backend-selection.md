# Backend Selection

`docguard` has five semantic-scan backends. The regex pass always runs first (free, offline, deterministic). The LLM pass is optional and pluggable.

## Auto-selection order

When you invoke `--semantic` without `--backend`, or `SanitizeConfig(semantic=True)` without `backend=...`:

1. `DOCGUARD_BACKEND` environment variable (exact name match)
2. `ANTHROPIC_API_KEY` set → `anthropic` backend
3. `OPENAI_API_KEY` set → `openai` backend
4. `claude` CLI on PATH and responding → `claude-cli` backend (your Claude Max/Pro subscription)
5. Ollama server reachable on `OLLAMA_HOST` (default `http://localhost:11434`) → `ollama`
6. Fallback → `regex` only (still runs, always)

Run `docguard --list-backends` to see what's configured on this machine.

## When to pick what

| Situation | Pick |
|---|---|
| You have Claude Max/Pro and run on your own machine | `claude-cli` — uses your subscription, no key to manage |
| Production service, explicit billing | `anthropic` or `openai` (set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) |
| Air-gapped enterprise | `ollama` with `llama3.1:8b` or `qwen2.5:7b` |
| Fully deterministic, never-network CI pipeline | `regex` (explicit) |
| Non-English documents where you want strong semantic coverage | `anthropic` (Claude handles Turkish, Spanish, etc. well) |

## Default models

Override via `--model` / `SanitizeConfig(backend_model=...)`:

| Backend | Default |
|---|---|
| `anthropic` | `claude-haiku-4-5-20251001` |
| `claude-cli` | `claude-haiku-4-5-20251001` |
| `openai` | `gpt-4.1-mini` |
| `ollama` | `llama3.1:8b` |

For classification you want a fast, cheap model — the task is simple and Haiku/4.1-mini are more than capable.

## Cost ballpark

A typical 2000-word document produces ~2500 input tokens + <200 output tokens.

| Backend | Cost per doc (approx) | Cost per 100 docs |
|---|---|---|
| `regex` | $0 | $0 |
| `claude-cli` | $0 (uses your sub) | $0 |
| `anthropic` (Haiku 4.5) | ~$0.0025 | ~$0.25 |
| `openai` (gpt-4.1-mini) | ~$0.002 | ~$0.20 |
| `ollama` | electricity only | ~$0 |

## Rate-limit and quota notes

- **claude-cli** shares your Claude Max/Pro quota with interactive Claude Code sessions. Heavy batch days can collide. Fall back to `regex` (or buy an API key) if this becomes a problem.
- **anthropic / openai** have their own per-key rate limits. `docguard` makes one call per document.
- **ollama** is limited only by your hardware. A 7B model on modern hardware classifies ~1 doc/second.

## Environment variables summary

| Var | Purpose |
|---|---|
| `DOCGUARD_BACKEND` | Force a specific backend |
| `ANTHROPIC_API_KEY` | Enables `anthropic` backend |
| `OPENAI_API_KEY` | Enables `openai` backend |
| `OLLAMA_HOST` | Point `ollama` backend at a non-default host |

## Adding your own backend

1. Create `src/docguard/semantic/mybackend.py`.
2. Implement a class with `name`, `default_model`, `available()`, `classify(text, model=None) -> list[SemanticFlag]`.
3. Register in `src/docguard/semantic/dispatcher.py` `BACKEND_REGISTRY`.
4. Optionally add it to auto-selection order.
5. Write a test in `tests/test_backend_dispatcher.py`.

See `claude_cli.py` and `anthropic_api.py` for reference implementations.
