# Contributing to docguard

Thanks for your interest. Every contribution makes this safer.

## Quick dev setup

```bash
git clone https://github.com/knowledge-work-tools/docguard.git
cd docguard
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest -v
ruff check src tests
mypy src
```

## How to add a new hiding technique (most valuable contribution)

1. **Prove it.** Write a test-fixture generator in `tools/make_poisoned_*.py` that produces a file containing the vector. Commit the generator, not the binary.
2. **Detect it.** Add detection logic to the relevant stripper (`src/docguard/docx/strippers.py` or `src/docguard/pdf/strippers.py`). Always record a `Finding` with the right `action` (`stripped` / `flagged` / `logged`).
3. **Test it.** Add a test in `tests/test_docx_strippers.py` or `tests/test_pdf_strippers.py` asserting the technique is caught and doesn't survive in `clean_text`.
4. **Document it.** Add a row to the table in `README.md` and, if it's novel, a short section in `docs/attack-taxonomy.md`.

## How to add a new regex pattern

1. Add `(category, label, pattern)` to `PATTERNS` in `src/docguard/semantic/regex_only.py`.
2. Add at least one positive and one negative test case to `tests/test_regex.py`.
3. Keep patterns specific enough not to false-positive on legitimate writing.

## How to add a new semantic backend

See `docs/backend-selection.md` section "Adding your own backend" for the protocol and checklist.

## Code style

- `ruff check` must pass.
- `mypy src` is advisory for now (we're working toward strict).
- Follow the existing patterns for docstrings and typing.
- Keep dependencies lean — new backends go in `[project.optional-dependencies]`.

## Testing conventions

- Unit tests live alongside each layer's tests.
- End-to-end tests use the poisoned fixtures (auto-generated).
- Tests that need network or paid APIs are marked `@pytest.mark.slow` or `@pytest.mark.claude_cli` — they're skipped by default on CI.

## Commit messages

Plain English, imperative mood, one concern per commit.

## Pull requests

- One topic per PR.
- Include the test case that fails without your fix.
- Reference the issue.

## Licence

By contributing you agree your work is MIT-licensed under the same terms as the rest of the project.
