"""Command line interface: print a template, build a font from photos, validate a font."""

from __future__ import annotations

import argparse
import platform
import sys
from importlib import metadata
from pathlib import Path

from .bundle import install_skill, skill_text
from .install import WINDOWS_FONT_KEY, install_font
from .pipeline import build_from_photos, build_project, validate_font
from .template import DEFAULT_CHARACTERS, Layout, write_template


def _package_version() -> str:
    try:
        return metadata.version("handfont")
    except metadata.PackageNotFoundError:
        return "unknown"


def row_guide(characters: str) -> list[str]:
    """The rows to copy onto plain paper, as printed after ``handfont template``."""
    columns = Layout().columns
    rows = [characters[start : start + columns] for start in range(0, len(characters), columns)]
    return [f"{index:>3}   {'  '.join(row)}" for index, row in enumerate(rows, 1)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="handfont", description="Turn a photo of your handwriting into a font"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser(
        "template", help="print a sheet to write on, or show the rows to copy onto any paper"
    )
    template.add_argument("--output", type=Path, default=Path("template"))
    template.add_argument(
        "--characters", default=DEFAULT_CHARACTERS, help="characters to include, in writing order"
    )
    template.add_argument("--title", default="handfont template")
    build = commands.add_parser("build", help="turn photos of your handwriting into font files")
    build.add_argument(
        "--photo",
        required=True,
        action="append",
        type=Path,
        help="JPEG or PNG photo of a filled-in template page or of the rows on plain paper;"
        " repeat for several pages",
    )
    build.add_argument("--family", required=True, help='font family name, such as "Ada Hand"')
    build.add_argument("--output", type=Path, default=Path("output"))
    build.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="crop map to use instead of automatic detection, such as output/manifest.json"
        " from an earlier build or a hand-made map",
    )
    build.add_argument(
        "--characters",
        default=None,
        help="the character set the template or rows were written with (default: printable ASCII)",
    )
    check = commands.add_parser("validate", help="check a built TrueType or WOFF2 font")
    check.add_argument("font", type=Path)
    check.add_argument("--manifest", type=Path, default=None)
    install = commands.add_parser("install", help="install a built TTF for your desktop apps")
    install.add_argument("font", type=Path)
    skill = commands.add_parser(
        "skill", help="print the skill that lets an AI coding agent run handfont for you"
    )
    skill.add_argument(
        "--install",
        type=Path,
        default=None,
        metavar="PROJECT",
        help="write it to PROJECT/.claude/skills/handfont/SKILL.md instead of printing it",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            paths = write_template(args.output, args.characters, args.title)
            print(f"Template: {paths[0]} ({len(paths) - 1} page(s), PNG copies alongside)")
            print("Print it, write one character per box, photograph each page, then run:")
            print('  handfont build --photo photo.jpg --family "Your Name Hand"')
            print()
            print("No printer? Copy these rows onto any paper, one row per line, with clear gaps")
            print("between characters and between rows, then photograph the page and run the same:")
            print("\n".join(row_guide(args.characters)))
        elif args.command == "build":
            if args.manifest is not None:
                if len(args.photo) != 1:
                    raise ValueError("--manifest describes exactly one photo")
                if args.characters is not None:
                    raise ValueError(
                        "--characters applies to template or plain-paper photos, not to --manifest builds"
                    )
                result = build_project(args.photo[0], args.manifest, args.output, args.family)
            else:
                characters = DEFAULT_CHARACTERS if args.characters is None else args.characters
                result = build_from_photos(args.photo, args.output, args.family, characters)
            source = {"template": "the printed template", "paper": "rows on plain paper"}
            print(
                f"Built {result.glyph_count} traced glyphs from {source.get(result.mode, 'the crop map')}: {result.ttf}"
            )
            if result.skipped:
                print(f"Empty cells skipped: {' '.join(result.skipped)}")
            if result.clipped:
                print(
                    f"Ink reached the edge of the box for: {' '.join(result.clipped)} (only what was inside is kept)"
                )
            if result.missing_pages:
                pages = ", ".join(str(page) for page in result.missing_pages)
                print(f"Pages not photographed: {pages}")
            for note in result.notes:
                print(f"Note: {note}")
            print(f"Web font: {result.woff2}")
            print(f"Preview: {result.preview}")
            print(f"Archive: {result.archive}")
            if result.layout_check is not None:
                print(f"Check which mark became which character: {result.layout_check}")
            if result.sheet is not None:
                print(f"Straightened sheet and crop map: {result.sheet}, {result.manifest}")
                print("Edit the crop map and rebuild with --manifest to refine individual letters.")
            print(f"npm package for websites and apps: {result.package} (see its SKILL.md)")
            print(f"Desktop install: handfont install {result.ttf}")
        elif args.command == "install":
            destination = install_font(args.font)
            print(f"Installed {destination}")
            if platform.system() == "Windows":
                print(
                    "Restart applications to see the font. To uninstall, delete the file and"
                    f" its value under HKEY_CURRENT_USER\\{WINDOWS_FONT_KEY}."
                )
            else:
                print("Restart applications to see the font. Remove the file to uninstall it.")
        elif args.command == "skill":
            if args.install is None:
                print(skill_text(), end="")
            else:
                path = install_skill(args.install)
                print(f"Skill written: {path}")
                print("Agents in that project can now be asked to make a handwriting font.")
        else:
            result = validate_font(args.font, args.manifest)
            print(f"Valid font: {result['characters']} characters, {result['glyphs']} glyphs")
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
