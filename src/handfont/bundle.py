"""Turn a built font into an npm package that carries its own skill for applying it."""

from __future__ import annotations

import json
import re
import shutil
from importlib import metadata, resources
from pathlib import Path
from string import Template


def package_name(family: str) -> str:
    """An npm package name for a family: lowercase, hyphenated, starting with a letter."""
    slug = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        return "handwriting-font"
    if not slug[0].isalpha():
        slug = f"font-{slug}"
    return slug[:214]


def npm_version(version: str) -> str:
    """The manifest's ``M.m`` design version as a semantic version."""
    major, minor = version.split(".")
    return f"{int(major)}.{int(minor)}.0"


def _render(template: str, **values: str) -> str:
    text = resources.files("handfont").joinpath("templates", template).read_text(encoding="utf-8")
    return Template(text).substitute(values)


def release_tag() -> str:
    """The Git tag the skills pin: ``v`` plus the installed package version."""
    try:
        return f"v{metadata.version('handfont')}"
    except metadata.PackageNotFoundError:
        return "main"


def skill_text() -> str:
    """The skill that teaches an AI coding agent to run handfont for someone."""
    return _render("handfont-skill.md", tag=release_tag())


def _clear_package(root: Path) -> None:
    """Remove an earlier handfont package, but never a folder someone else wrote."""
    if not root.exists():
        return
    manifest = root / "package.json"
    try:
        keywords = json.loads(manifest.read_text(encoding="utf-8")).get("keywords", [])
    except OSError, ValueError:
        keywords = []
    if "handfont" not in keywords:
        raise ValueError(f"{root} exists and was not written by handfont; choose another --output")
    shutil.rmtree(root)


def install_skill(project: Path) -> Path:
    """Write the handfont skill where Claude Code discovers project skills."""
    path = Path(project) / ".claude" / "skills" / "handfont" / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(skill_text(), encoding="utf-8")
    return path


def write_package(
    output: Path,
    family: str,
    ttf: Path,
    woff2: Path,
    characters: str,
    aliases: dict[str, str],
    version: str,
    license: str | None = None,
    license_file: Path | None = None,
) -> Path:
    """Write ``output/package``: fonts, CSS, a JS entry, a README, a skill and an AGENTS block."""
    name = package_name(family)
    stem = ttf.stem.removesuffix("-Regular")
    root = Path(output) / "package"
    _clear_package(root)
    (root / "fonts").mkdir(parents=True)
    shutil.copyfile(ttf, root / "fonts" / ttf.name)
    shutil.copyfile(woff2, root / "fonts" / woff2.name)
    css_family = family.replace("\\", "\\\\").replace('"', '\\"')
    (root / "index.css").write_text(
        "@font-face {\n"
        f'  font-family: "{css_family}";\n'
        f'  src: url("./fonts/{woff2.name}") format("woff2");\n'
        "  font-weight: 400;\n"
        "  font-style: normal;\n"
        "  font-display: swap;\n"
        "}\n",
        encoding="utf-8",
    )
    stack = json.dumps(f'"{family}", system-ui, sans-serif')
    (root / "index.js").write_text(
        f"export const family = {json.dumps(family)};\n"
        f"export const fontFamily = {stack};\n"
        f'export const files = {{ woff2: "fonts/{woff2.name}", ttf: "fonts/{ttf.name}" }};\n'
        f"export const characters = {json.dumps(characters, ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    (root / "index.d.ts").write_text(
        "export const family: string;\n"
        "export const fontFamily: string;\n"
        "export const files: { woff2: string; ttf: string };\n"
        "export const characters: string;\n",
        encoding="utf-8",
    )
    manifest = {
        "name": name,
        "version": npm_version(version),
        "description": f"{family}, a handwriting font built with handfont",
        "license": license or "UNLICENSED",
        "type": "module",
        "main": "index.js",
        "types": "index.d.ts",
        "style": "index.css",
        "exports": {
            ".": "./index.js",
            "./index.css": "./index.css",
            "./fonts/*": "./fonts/*",
            "./package.json": "./package.json",
        },
        "sideEffects": ["*.css"],
        "files": [
            "fonts",
            "index.css",
            "index.js",
            "index.d.ts",
            "SKILL.md",
            "AGENTS.md",
            *(["LICENSE.txt"] if license_file else []),
        ],
        "keywords": ["font", "handwriting", "handfont", name],
    }
    (root / "package.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    mapped = ", ".join(f"{alias} -> {source}" for alias, source in aliases.items() if source != " ")
    if license_file is not None:
        shutil.copyfile(license_file, root / "LICENSE.txt")
    if license:
        terms = (
            f"Licensed under the {license} license; see LICENSE.txt. The font may be used,\n"
            "embedded, bundled and modified freely, but not sold by itself, and modified versions\n"
            "may not use its reserved name."
        )
    else:
        terms = (
            "No license has been chosen yet (`UNLICENSED` in package.json). Pick one before\n"
            "sharing the package with others, for example the SIL Open Font License, and record\n"
            "it here."
        )
    values = {
        "family": family,
        "name": name,
        "slug": name,
        "stem": stem,
        "characters": characters,
        "aliases": f"Also mapped onto written characters: {mapped}.\n" if mapped else "",
        "tag": release_tag(),
        "license": terms,
    }
    (root / "README.md").write_text(_render("package-readme.md", **values), encoding="utf-8")
    (root / "SKILL.md").write_text(_render("use-font.md", **values), encoding="utf-8")
    (root / "AGENTS.md").write_text(_render("package-agents.md", **values), encoding="utf-8")
    return root
