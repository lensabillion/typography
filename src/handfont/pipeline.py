"""Public build and validation operations."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

from .artifacts import (
    write_archive,
    write_build_info,
    write_css,
    write_layout_check,
    write_license,
    write_preview,
    write_readme,
    write_tester,
    write_tracing_sheet,
)
from .bundle import write_package
from .capture import Capture, capture_page, detect_page, find_markers, measure, resolution_note
from .font import build_font, font_stem
from .freehand import LayoutError, capture_freehand
from .manifest import Manifest, check_license, load_manifest, manifest_to_dict
from .template import DEFAULT_CHARACTERS, Layout, check_characters
from .tracing import load_image, trace_glyphs


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
    manifest: Path
    package: Path
    glyph_count: int
    license: Path | None = None
    mode: str = "manifest"
    skipped: tuple[str, ...] = ()
    missing_pages: tuple[int, ...] = ()
    clipped: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    sheet: Path | None = None
    layout_check: Path | None = None


def licensed(manifest: Manifest, copyright: str | None, license: str | None) -> Manifest:
    """Apply a copyright notice and license from the command line on top of a manifest."""
    if copyright is None and license is None:
        return manifest
    copyright = manifest.copyright if copyright is None else copyright
    license = manifest.license if license is None else license
    check_license(copyright, license)
    return replace(manifest, copyright=copyright, license=license)


def build_project(
    photo: Path,
    manifest_path: Path,
    output: Path,
    family: str,
    *,
    copyright: str | None = None,
    license: str | None = None,
) -> BuildResult:
    """Trace a photograph using a hand-written crop map and produce every deliverable."""
    photo, manifest_path, output = Path(photo), Path(manifest_path), Path(output)
    manifest = licensed(load_manifest(manifest_path), copyright, license)
    font_stem(family)  # Reject an unusable family name before the slow tracing step.
    glyphs = trace_glyphs(photo, manifest)
    output.mkdir(parents=True, exist_ok=True)
    return _assemble(manifest, manifest_path, glyphs, output, family, [photo], "manifest")


def build_from_photos(
    photos: Sequence[Path],
    output: Path,
    family: str,
    characters: str = DEFAULT_CHARACTERS,
    *,
    copyright: str | None = None,
    license: str | None = None,
) -> BuildResult:
    """Build from photographs of either the printed template or rows on plain paper.

    Photos showing the template's corner markers go through the template path; photos
    without markers are read as rows of characters written on any paper.
    """
    photos = [Path(photo) for photo in photos]
    font_stem(family)
    check_characters(characters)
    check_license(copyright, license)
    pages = [detect_page(find_markers(load_image(photo))) for photo in photos]
    if all(page is not None for page in pages):
        return build_from_template(
            photos, output, family, characters, copyright=copyright, license=license
        )
    if any(page is not None for page in pages):
        raise ValueError(
            "Some photos show the printed template and some show plain paper; build them separately"
        )
    return build_from_paper(
        photos, output, family, characters, copyright=copyright, license=license
    )


def build_from_template(
    photos: Sequence[Path],
    output: Path,
    family: str,
    characters: str = DEFAULT_CHARACTERS,
    *,
    copyright: str | None = None,
    license: str | None = None,
) -> BuildResult:
    """Build a font from photographs of filled-in template pages; no crop map is needed.

    The straightened sheet and the derived crop map are written next to the font so
    the build can be refined by hand and repeated with :func:`build_project`.
    """
    photos = [Path(photo) for photo in photos]
    font_stem(family)
    check_characters(characters)
    layout = Layout()
    pages = [capture_page(photo, layout) for photo in photos]
    capture = measure(pages, characters, layout)
    capture = replace(capture, manifest=licensed(capture.manifest, copyright, license))
    notes = tuple(note for page in pages if (note := resolution_note(page, layout)))
    return _finish(capture, Path(output), family, photos, "template", notes)


def build_from_paper(
    photos: Sequence[Path],
    output: Path,
    family: str,
    characters: str = DEFAULT_CHARACTERS,
    *,
    copyright: str | None = None,
    license: str | None = None,
) -> BuildResult:
    """Build a font from photographs of the character rows written on any paper.

    ``layout-check.png`` shows which mark became which character; when the rows cannot
    be matched, the marks that were found are numbered in that image instead.
    """
    photos, output = [Path(photo) for photo in photos], Path(output)
    font_stem(family)
    check_characters(characters)
    output.mkdir(parents=True, exist_ok=True)
    try:
        capture = capture_freehand(photos, characters, Layout().columns)
    except LayoutError as exc:
        numbered = [(str(index + 1), box) for index, box in enumerate(exc.boxes)]
        check = write_layout_check(exc.sheet, numbered, output)
        raise ValueError(f"{exc}. The marks that were found are numbered in {check}") from exc
    capture = replace(capture, manifest=licensed(capture.manifest, copyright, license))
    result = _finish(capture, output, family, photos, "paper")
    labelled = [(glyph.character, glyph.box) for glyph in capture.manifest.glyphs]
    return replace(result, layout_check=write_layout_check(capture.sheet, labelled, output))


def _finish(
    capture: Capture,
    output: Path,
    family: str,
    photos: Sequence[Path],
    mode: str,
    notes: tuple[str, ...] = (),
) -> BuildResult:
    output.mkdir(parents=True, exist_ok=True)
    sheet = output / "sheet.png"
    manifest_path = output / "manifest.json"
    Image.fromarray(capture.sheet).save(sheet)
    manifest_path.write_text(
        json.dumps(manifest_to_dict(capture.manifest), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        result = _assemble(
            capture.manifest,
            manifest_path,
            capture.masks,
            output,
            family,
            photos,
            mode,
            capture.skipped,
            capture.clipped,
        )
    except Exception:
        sheet.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    return replace(
        result,
        missing_pages=capture.missing_pages,
        clipped=capture.clipped,
        notes=notes,
        sheet=sheet,
    )


def _assemble(
    manifest: Manifest,
    manifest_path: Path,
    glyphs: dict[str, np.ndarray],
    output: Path,
    family: str,
    sources: Sequence[Path],
    mode: str,
    skipped: tuple[str, ...] = (),
    clipped: tuple[str, ...] = (),
) -> BuildResult:
    characters = "".join(spec.character for spec in manifest.glyphs)
    ttf, woff2 = build_font(manifest, glyphs, output, family)
    css = write_css(woff2, output, family)
    preview = write_preview(ttf, output, family, characters)
    tracing_sheet = write_tracing_sheet(glyphs, output)
    tester = write_tester(ttf, woff2, output, family, characters, skipped)
    license_file = None
    if manifest.license is not None and manifest.copyright is not None:
        license_file = write_license(output, family, manifest.copyright, manifest.license)
    readme = write_readme(
        output, family, ttf, woff2, characters, manifest.aliases, skipped, manifest.license
    )
    build_info = write_build_info(
        sources, manifest_path, output, family, len(glyphs), mode, skipped, clipped
    )
    validate_font(ttf, manifest_path)
    validate_font(woff2, manifest_path)
    with TTFont(ttf) as desktop, TTFont(woff2) as web:
        if (
            desktop.getBestCmap() != web.getBestCmap()
            or desktop["hmtx"].metrics != web["hmtx"].metrics
        ):
            raise ValueError("TTF and WOFF2 character maps or advances disagree")
    package = write_package(
        output,
        family,
        ttf,
        woff2,
        characters,
        manifest.aliases,
        manifest.version,
        manifest.license,
        license_file,
    )
    packaged = [
        (str(path.relative_to(output)), path)
        for path in sorted(package.rglob("*"))
        if path.is_file()
    ]
    deliverables = [ttf, woff2, css, preview, tracing_sheet, tester, readme, build_info]
    if license_file is not None:
        deliverables.append(license_file)
    archive = write_archive([*deliverables, *packaged], output, ttf.stem.removesuffix("-Regular"))
    return BuildResult(
        ttf,
        woff2,
        css,
        preview,
        tracing_sheet,
        tester,
        readme,
        build_info,
        archive,
        manifest_path,
        package,
        len(glyphs),
        license_file,
        mode,
        skipped,
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
        glyf, hmtx = font["glyf"], font["hmtx"]
        drawn = [name for name in glyph_names if getattr(glyf[name], "numberOfContours", 0) > 0]
        if any(hmtx[name][1] != glyf[name].xMin for name in drawn):
            raise ValueError("A left side bearing disagrees with its glyph outline")
        if font["head"].unitsPerEm != 1000:
            raise ValueError("Unexpected units per em")
        if (
            font["hhea"].ascent != font["OS/2"].sTypoAscender
            or font["hhea"].descent != font["OS/2"].sTypoDescender
            or font["hhea"].lineGap != font["OS/2"].sTypoLineGap
        ):
            raise ValueError("Horizontal and typographic metrics disagree")
        if any(advance <= 0 for advance, _ in hmtx.metrics.values()):
            raise ValueError("Font has a nonpositive glyph advance")
        if font["OS/2"].fsType != 0 or not font["OS/2"].fsSelection & (1 << 6):
            raise ValueError("Font embedding or Regular style flags are invalid")
        mapped_names = set(cmap.values()) - {"space"}
        if any(getattr(glyf[name], "numberOfContours", 0) <= 0 for name in mapped_names):
            raise ValueError("A mapped character has no visible outlines")
        upper = font["OS/2"].usWinAscent
        lower = -font["OS/2"].usWinDescent
        if any(
            glyph.yMin < lower
            or glyph.yMax > upper
            or glyph.yMin < font["hhea"].descent
            or glyph.yMax > font["hhea"].ascent
            for glyph in glyf.glyphs.values()
            if getattr(glyph, "numberOfContours", 0) > 0
        ):
            raise ValueError("Glyph extents exceed OS/2 or hhea clipping bounds")
        return {"path": str(path), "characters": len(cmap), "glyphs": len(glyph_names)}
    finally:
        font.close()
