# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for potential security vulnerabilities.

Report privately via GitHub's "Security → Report a vulnerability" flow, or by opening an issue labelled `security` with only a brief summary and a request for a private channel.

We consider the following in scope:

- A document that bypasses `docguard`'s stripping and leaves hidden content in `clean_text` or `clean.pdf` / `clean.docx`
- A document that causes `docguard` to crash with unhandled exceptions (DoS surface for anyone hosting docguard behind an upload endpoint)
- A semantic backend implementation that leaks document content outside the classifier call

Out of scope:
- Social-engineering attacks on humans downstream of docguard
- Jailbreaks of LLMs that docguard never processes
- Vulnerabilities in dependencies (`python-docx`, `pymupdf`, etc.) — please report those to the upstream project

## Response SLA

This is a volunteer-maintained project. Expect acknowledgement within 7 days; a fix or mitigation within 30 days for high-severity reports.

## Disclosure

Please give us reasonable time to ship a fix before public disclosure. Coordinated disclosure is appreciated.
