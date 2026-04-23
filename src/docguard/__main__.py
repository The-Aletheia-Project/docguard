"""Allow `python -m docguard` to invoke the CLI."""

from docguard.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
