# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-23

### Added

- Initial release.
- DOCX sanitizer covering `w:vanish` (inline + style chain), white-on-white text, sub-threshold font size, `w:altChunk`, `mc:Fallback`, off-page text boxes, comments, tracked changes, metadata.
- PDF sanitizer covering white-ink text, near-zero alpha, sub-1pt font, annotations (`/Contents`), form-field widgets, JavaScript actions (flagged), invisible OCG layers (flagged), embedded files (flagged), metadata.
- Unicode hygiene: strip Unicode Tags block (U+E0000–U+E007F), variant selectors, bidi overrides, zero-width / invisible-math, BOM. Log homoglyphs.
- Regex semantic scan bank with EN + Turkish patterns for direct instructions, goal manipulation, persona hijack, system-prompt leakage, data exfiltration.
- Five pluggable LLM backends: `regex`, `claude-cli` (subscription), `anthropic`, `openai`, `ollama`. Auto-selection by env / PATH.
- Spotlighting wrapper (Hines et al., 2024) with three modes: datamark, base64, delimit.
- Public Python API: `sanitize()`, `SanitizeConfig`, `SanitizeResult`.
- CLI entry point (`docguard`) with single-file and batch modes.
- JSON report sidecar + CSV summary for batch runs.
- Example integrations for LangChain, LlamaIndex, and Flask.
- 43-test pytest suite covering all layers.

### Known limitations

- Off-CropBox text in PDFs is not re-extracted if pymupdf skips it at extraction time.
- No render-vs-OCR diff yet (planned for v0.2.0).
- No malicious-font cmap detection (planned for v0.2.0).
- Homoglyph detection is log-only (by design; false-positive risk on non-Latin scripts).
- `claude-cli` backend shares subscription quota with interactive Claude Code sessions.
