"""Public build and validation operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont

from .artifacts import (
    write_archive,
    write_build_info,
    write_css,
    write_preview,
    write_readme,
    write_tester,
    write_tracing_sheet,
)
from .font import build_font
from .manifest import load_manifest
from .tracing import trace_glyphs


@dataclass(frozen=True)
class BuildResult:
    ttf: Path
    woff2: Path
    css: Path
    preview: Path
    tracing_sheet: Path
    tester: Path
    readme: Path
    build_info: Path
    archive: Path
    glyph_count: int


def build_project(
    source: Path, manifest_path: Path, output: Path, family: str = "Lensa Hand"
) -> BuildResult:
    """Trace the photo and produce a font plus review and distribution artifacts."""
    source, manifest_path, output = Path(source), Path(manifest_path), Path(output)
    manifest = load_manifest(manifest_path)
    glyphs = trace_glyphs(source, manifest)
    output.mkdir(parents=True, exist_ok=True)
    ttf, woff2 = build_font(manifest, glyphs, output, family)
    css = write_css(woff2, output, family)
    preview = write_preview(ttf, output, family)
    tracing_sheet = write_tracing_sheet(glyphs, output)
    tester = write_tester(ttf, woff2, output, family)
    readme = write_readme(output, family, ttf, woff2)
    build_info = write_build_info(source, manifest_path, output, family, len(glyphs))
    validate_font(ttf, manifest_path)
    validate_font(woff2, manifest_path)
    with TTFont(ttf) as desktop, TTFont(woff2) as web:
        if (
            desktop.getBestCmap() != web.getBestCmap()
            or desktop["hmtx"].metrics != web["hmtx"].metrics
        ):
            raise ValueError("TTF and WOFF2 character maps or advances disagree")
    archive = write_archive(
        [ttf, woff2, css, preview, tracing_sheet, tester, readme, build_info],
        output,
        ttf.stem.removesuffix("-Regular"),
    )
    return BuildResult(
        ttf, woff2, css, preview, tracing_sheet, tester, readme, build_info, archive, len(glyphs)
    )


def validate_font(path: Path, manifest_path: Path | None = None) -> dict[str, int | str]:
    """Check that the built font opens and exposes its expected character map."""
    path = Path(path)
    try:
        font = TTFont(path, recalcTimestamp=False)
    except Exception as exc:
        raise ValueError(f"Cannot open font {path}: {exc}") from exc
    try:
        required_tables = {"cmap", "glyf", "head", "hhea", "hmtx", "maxp", "name", "OS/2", "post"}
        missing_tables = sorted(required_tables - set(font.keys()))
        if missing_tables:
            raise ValueError(f"Font lacks required tables: {', '.join(missing_tables)}")
        cmap = font.getBestCmap()
        if not cmap or 32 not in cmap:
            raise ValueError("Font lacks a usable character map or space")
        if manifest_path is not None:
            manifest = load_manifest(Path(manifest_path))
            expected = {ord(spec.character) for spec in manifest.glyphs}
            expected.update(ord(character) for character in manifest.aliases)
            expected.update({32, 160})
            missing = expected - set(cmap)
            if missing:
                raise ValueError(
                    "Font lacks expected characters: "
                    + ", ".join(f"U+{value:04X}" for value in sorted(missing))
                )
        glyph_names = set(font.getGlyphOrder())
        if any(glyph not in glyph_names for glyph in cmap.values()):
            raise ValueError("Character map points to a missing glyph")
        if font["head"].unitsPerEm != 1000:
            raise ValueError("Unexpected units per em")
        if (
            font["hhea"].ascent != font["OS/2"].sTypoAscender
            or font["hhea"].descent != font["OS/2"].sTypoDescender
            or font["hhea"].lineGap != font["OS/2"].sTypoLineGap
        ):
            raise ValueError("Horizontal and typographic metrics disagree")
        if any(advance <= 0 for advance, _ in font["hmtx"].metrics.values()):
            raise ValueError("Font has a nonpositive glyph advance")
        if font["OS/2"].fsType != 0 or not font["OS/2"].fsSelection & (1 << 6):
            raise ValueError("Font embedding or Regular style flags are invalid")
        mapped_names = set(cmap.values()) - {"space"}
        if any(getattr(font["glyf"][name], "numberOfContours", 0) <= 0 for name in mapped_names):
            raise ValueError("A mapped character has no visible outlines")
        upper = font["OS/2"].usWinAscent
        lower = -font["OS/2"].usWinDescent
        if any(
            glyph.yMin < lower
            or glyph.yMax > upper
            or glyph.yMin < font["hhea"].descent
            or glyph.yMax > font["hhea"].ascent
            for glyph in font["glyf"].glyphs.values()
            if getattr(glyph, "numberOfContours", 0) > 0
        ):
            raise ValueError("Glyph extents exceed OS/2 or hhea clipping bounds")
        return {"path": str(path), "characters": len(cmap), "glyphs": len(glyph_names)}
    finally:
        font.close()
