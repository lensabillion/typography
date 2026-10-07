"""Compatibility entry point; prefer ``uv run handfont build``."""

from handfont.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
