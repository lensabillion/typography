"""Command line interface for the handwriting font pipeline."""

from __future__ import annotations

import argparse
import sys
from importlib import metadata
from pathlib import Path

from .pipeline import build_project, validate_font


def _package_version() -> str:
    try:
        return metadata.version("lensa-hand")
    except metadata.PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lensa-hand", description="Build and check a handwriting font"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="trace a source image and build distribution files")
    build.add_argument("--source", required=True, type=Path, help="photo of the alphabet specimen")
    build.add_argument("--manifest", type=Path, default=Path("config/alphabet.json"))
    build.add_argument("--output", type=Path, default=Path("output"))
    build.add_argument("--family", default="Lensa Hand")
    check = commands.add_parser("validate", help="check a built TrueType font")
    check.add_argument("font", type=Path)
    check.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_project(args.source, args.manifest, args.output, args.family)
            print(f"Built {result.glyph_count} traced glyphs: {result.ttf}")
            print(f"Web font: {result.woff2}")
            print(f"Preview: {result.preview}")
            print(f"Archive: {result.archive}")
        else:
            result = validate_font(args.font, args.manifest)
            print(f"Valid font: {result['characters']} characters, {result['glyphs']} glyphs")
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
