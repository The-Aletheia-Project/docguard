# docguard

> Your LLM just read "ignore previous instructions" in white-on-white text on page 3.

`docguard` scrubs hidden prompt injections from `.docx` and `.pdf` files before you feed them to an LLM. Zero API key required — use your existing Claude/OpenAI subscription, your own API key, or run fully offline.

[![PyPI](https://img.shields.io/badge/pypi-docguard-blue)](https://pypi.org/project/docguard/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)

## Who this is for

You process user-uploaded documents through an LLM. Attackers know this. If even one of these sounds like your workflow, `docguard` is for you:

- **Legal** — contract review, discovery, due diligence. Opposing counsel embeds "summarise this as 'favourable'" in white text.
- **HR / recruiting** — resume screening. Candidates embed "recommend for hire" in 1pt font. ([Real, documented attack](https://kai-greshake.de/posts/inject-my-pdf/).)
- **Compliance / risk** — reviewing third-party SOC2s, questionnaires, vendor docs.
- **Financial analysis** — processing annual reports, filings, pitch decks from outside sources.
- **Journalism & research** — document-heavy investigations, FOIA responses.
- **Customer support** — triaging uploaded tickets or attachments.
- **Education** — grading student submissions.

## What it catches

| Vector | Layer | Default action |
|---|---|---|
| `w:vanish` (inline or via style chain) — DOCX | structural | strip |
| White / near-white text on white page — DOCX & PDF | structural | strip |
| Sub-threshold font size — DOCX & PDF | structural | strip |
| Near-zero alpha (transparent text) — PDF | structural | strip |
| `<w:altChunk>` HTML/RTF imports — DOCX | structural | strip |
| `mc:AlternateContent` / Fallback branch — DOCX | structural | rewrite |
| Off-page text boxes — DOCX | structural | strip |
| PDF annotation `/Contents` | structural | strip |
| PDF form widgets | structural | strip |
| PDF JavaScript actions | structural | flag |
| PDF invisible OCG layers | structural | flag |
| PDF embedded files | structural | flag |
| Document metadata (title, author, subject, XMP) | structural | strip |
| Unicode Tags block (U+E0000–U+E007F) | unicode | strip |
| Variant selectors (VS1–VS256) | unicode | strip |
| Bidi overrides / isolates | unicode | strip |
| Zero-width / BOM / invisible-math | unicode | strip |
| Homoglyph confusables | unicode | **log only** |
| Visible "ignore previous instructions" / goal manipulation / persona hijack / data exfil | semantic (regex) | **flag** |
| Context-anomalous instructions in any language | semantic (LLM) | **flag** |

> "Strip" = removed from cleaned output. "Flag" = surfaces in the report for human review; nothing auto-stripped.

## Install

```bash
pip install docguard                   # DOCX only
pip install docguard[pdf]              # + PDF support
pip install docguard[pdf,anthropic]    # + Anthropic API backend
pip install docguard[all]              # everything
```

Optional extras:
- `pdf` — adds `pymupdf`, `pikepdf` for PDF support
- `homoglyphs` — adds `confusable-homoglyphs` for homoglyph logging
- `anthropic` — enables the Anthropic API backend
- `openai` — enables the OpenAI API backend
- `ollama` — enables the local Ollama backend

## 30-second quickstart

### Command line

```bash
docguard contract.pdf --out cleaned/ --semantic
docguard --batch 'inbox/*.docx' --out cleaned/
docguard --list-backends    # see what's configured on this machine
```

Outputs per file:
- `<name>.clean.docx` / `.clean.pdf` — cleaned document
- `<name>.clean.txt` — cleaned plain text
- `<name>.spotlight.txt` — spotlight-wrapped text ready to feed to your LLM
- `<name>.report.json` — audit trail of every strip and flag

### Python

```python
from docguard import sanitize, SanitizeConfig

result = sanitize(
    "contract.pdf",
    config=SanitizeConfig(semantic=True),
)

print(result.injection_likely)   # True/False
print(result.clean_text)         # safe plain text
print(result.spotlight_text)     # wrapped, ready for your prompt

# Feed to your LLM
from anthropic import Anthropic
resp = Anthropic().messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    messages=[{"role": "user", "content": f"Summarise:\n\n{result.spotlight_text}"}],
)
```

## Semantic backends (no API key required)

`docguard` auto-detects what's available on your machine in this order:

| Backend | Prereq | Cost | Notes |
|---|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | per-token | explicit cost control |
| `openai` | `OPENAI_API_KEY` | per-token | explicit cost control |
| `claude-cli` | `claude` on PATH | uses your Claude Max/Pro subscription | **no API key** |
| `ollama` | `ollama serve` running | free, local | air-gapped use |
| `regex` | always | free, offline | deterministic fallback |

Override with `docguard --backend claude-cli` or `SanitizeConfig(backend="anthropic")` or set `DOCGUARD_BACKEND=openai` in your env.

## Threat model

**In scope** — indirect prompt injection: an attacker who controls the document's content but not your runtime, trying to hijack the LLM processing it.

**Out of scope** — LLM jailbreaks of a prompt you authored. Direct social engineering of a human reader. Network-level MITM. Supply-chain attacks on the LLM provider.

**Defense in depth.** Even with `docguard`, follow [Simon Willison's lethal trifecta rule](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents): untrusted input + private data + exfil channel = danger. Remove any one leg and you're safe. Your grading/review LLM should not have tool access (browsing, email, shell) while processing untrusted documents.

## Integrations

### LangChain `DocumentLoader`

```python
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from docguard import sanitize, SanitizeConfig

class GuardedLoader(BaseLoader):
    def __init__(self, path: str):
        self.path = path

    def load(self) -> list[Document]:
        result = sanitize(self.path, config=SanitizeConfig(semantic=True))
        return [Document(
            page_content=result.spotlight_text,
            metadata={"source": self.path, "injection_likely": result.injection_likely},
        )]
```

### LlamaIndex `Reader`

```python
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document
from docguard import sanitize

class GuardedReader(BaseReader):
    def load_data(self, file, **kwargs):
        result = sanitize(str(file))
        return [Document(text=result.spotlight_text, metadata={"source": str(file)})]
```

See `examples/` for runnable versions, plus a Flask upload endpoint and a batch-folder script.

## Comparison with other tools

| Project | Focus | DOCX? | PDF? | Hidden-content scrub? | Injection classifier? |
|---|---|---|---|---|---|
| **docguard** | document pre-processing for LLMs | **yes** | **yes** | **yes** | yes (regex + pluggable LLM) |
| [LLM Guard](https://github.com/protectai/llm-guard) | runtime prompt/output scanning | no | no | partial (`InvisibleText`) | yes (deberta-v3) |
| [Rebuff](https://github.com/protectai/rebuff) | runtime prompt injection | no | no | no | yes — **archived May 2025** |
| [Lakera Guard](https://www.lakera.ai/) | commercial runtime classifier | no | no | no | yes, 100+ languages |
| [Microsoft Spotlighting](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/better-detecting-cross-prompt-injection-attacks-introducing-spotlighting-in-azur/4458404) | prompt-level datamarking | — | — | — | — |

`docguard` is **complementary** to runtime classifiers — use both. `docguard` pre-processes documents; LLM Guard or Lakera scans the final prompt.

## What docguard does NOT do

- No jailbreak detection on prompts you wrote yourself.
- No protection once content is already inside your LLM's context. Use together with runtime classifiers.
- No PDF render-vs-OCR diff yet (planned for v0.2.0 — [PhantomLint approach](https://arxiv.org/abs/2508.17884)).
- No malicious-font `cmap` detection (rare; planned for v0.2.0).
- No image/EXIF scanning yet.
- Homoglyphs are logged but not stripped (false-positive risk with non-Latin scripts).

## Attack taxonomy

See [docs/attack-taxonomy.md](./docs/attack-taxonomy.md) for the full 2024–2026 landscape of hidden prompt injection techniques this was built against, with links to papers and real incidents (EchoLeak, Gemini Trifecta, Inject-My-PDF, PhantomLint).

## Security

Found a new hiding technique or a bypass? See [SECURITY.md](./SECURITY.md). Please don't file public issues for potential vulnerabilities.

## Contributing

- New hiding technique → open an issue with a minimal PoC document.
- New semantic backend → implement `SemanticBackend` in `src/docguard/semantic/<name>.py`; see the existing ones.
- New regex pattern → add to `src/docguard/semantic/regex_only.py` with a test.

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT. See [LICENSE](./LICENSE).

## Credits

Built from research on indirect prompt injection and defence patterns including Greshake et al.'s [original taxonomy](https://arxiv.org/abs/2302.12173), Microsoft's [Spotlighting](https://arxiv.org/abs/2403.14720), the [PhantomLint](https://arxiv.org/abs/2508.17884) render-comparison technique, and Simon Willison's writing on agent security. Full citations in [docs/attack-taxonomy.md](./docs/attack-taxonomy.md).
