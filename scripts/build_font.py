"""Compatibility entry point; prefer ``uv run lensa-hand build``."""

from lensa_hand.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
