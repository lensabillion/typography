"""Draw TrueType outlines and write installable and web font files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import potrace
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program

from .manifest import Manifest


def _glyph_name(character: str) -> str:
    return f"uni{ord(character):04X}" if ord(character) <= 0xFFFF else f"u{ord(character):06X}"


def _notdef_glyph():
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((50, 650))
    pen.lineTo((400, 650))
    pen.lineTo((400, 0))
    pen.closePath()
    pen.moveTo((100, 100))
    pen.lineTo((350, 100))
    pen.lineTo((350, 550))
    pen.lineTo((100, 550))
    pen.closePath()
    return pen.glyph()


def _outline(mask: np.ndarray, height: int, bottom: int):
    rows, columns = mask.shape
    scale = height / rows
    pen = TTGlyphPen(None)
    # Potrace follows the pencil edge with cubic curves. FontTools converts those
    # curves to TrueType's quadratic outlines within one font unit of error.
    curves = potrace.Bitmap(255 - mask).trace(turdsize=1, alphamax=1.0)
    if not curves:
        raise ValueError("Traced glyph has no contours")

    def point(value):
        return (55 + value.x * scale, (rows - value.y) * scale + bottom)

    recordings: list[tuple[float, RecordingPen]] = []
    for curve in curves:
        if not curve.segments:
            continue
        record = RecordingPen()
        record.moveTo(point(curve.start_point))
        for segment in curve.segments:
            if segment.is_corner:
                record.lineTo(point(segment.c))
                record.lineTo(point(segment.end_point))
            else:
                record.curveTo(point(segment.c1), point(segment.c2), point(segment.end_point))
        record.closePath()
        area_pen = AreaPen()
        record.replay(area_pen)
        if abs(area_pen.value) > 1:
            recordings.append((area_pen.value, record))
    if not recordings:
        raise ValueError("Traced glyph has no usable outlines")
    # Potrace gives exterior and counter contours opposite winding. Use the
    # largest contour to orient every exterior clockwise in TrueType space.
    reverse = max(recordings, key=lambda pair: abs(pair[0]))[0] > 0
    for _, record in recordings:
        record.replay(Cu2QuPen(pen, max_err=1.0, reverse_direction=reverse))
    return pen.glyph(), (round(columns * scale + 110), 55)


def build_font(
    manifest: Manifest, glyphs: dict[str, np.ndarray], output: Path, family: str = "Lensa Hand"
) -> tuple[Path, Path]:
    if not family.strip():
        raise ValueError("Font family must not be blank")
    output.mkdir(parents=True, exist_ok=True)
    stem = "".join(character for character in family if character.isascii() and character.isalnum())
    if not stem or len(stem) > 55:
        raise ValueError("Font family must contain letters or numbers")
    ttf_path = output / f"{stem}-Regular.ttf"
    woff2_path = output / f"{stem}-Regular.woff2"
    builder = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef", "space", *(_glyph_name(spec.character) for spec in manifest.glyphs)]
    builder.setupGlyphOrder(glyph_order)
    cmap = {32: "space", 160: "space"}
    cmap.update({ord(spec.character): _glyph_name(spec.character) for spec in manifest.glyphs})
    cmap.update(
        {
            ord(alias): "space" if source == " " else _glyph_name(source)
            for alias, source in manifest.aliases.items()
        }
    )
    builder.setupCharacterMap(cmap)
    outlines = {".notdef": _notdef_glyph(), "space": TTGlyphPen(None).glyph()}
    metrics = {".notdef": (450, 50), "space": (320, 0)}
    for spec in manifest.glyphs:
        if spec.character not in glyphs:
            raise ValueError(f"Missing traced glyph {spec.character!r}")
        name = _glyph_name(spec.character)
        outlines[name], metrics[name] = _outline(glyphs[spec.character], spec.height, spec.bottom)
    bounds_top = max(spec.height + spec.bottom for spec in manifest.glyphs)
    bounds_bottom = min(spec.bottom for spec in manifest.glyphs)
    ascent = max(1150, bounds_top + 25)
    descent = -max(300, -bounds_bottom + 25)
    builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=0)
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{stem}-Regular-0.2",
            "fullName": f"{family} Regular",
            "psName": f"{stem}-Regular",
            "version": "Version 0.200",
        },
        mac=False,
    )
    builder.setupOS2(
        version=4,
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sTypoLineGap=0,
        usWinAscent=max(1150, bounds_top + 25),
        usWinDescent=max(350, -bounds_bottom + 25),
        sxHeight=430,
        sCapHeight=650,
        ySubscriptXSize=650,
        ySubscriptYSize=600,
        ySubscriptXOffset=0,
        ySubscriptYOffset=75,
        ySuperscriptXSize=650,
        ySuperscriptYSize=600,
        ySuperscriptXOffset=0,
        ySuperscriptYOffset=350,
        yStrikeoutSize=50,
        yStrikeoutPosition=250,
        ulCodePageRange1=1,
        ulCodePageRange2=0,
        fsSelection=(1 << 6) | (1 << 7),
        fsType=0,
    )
    builder.setupPost()
    builder.font["post"].underlinePosition = -100
    builder.font["post"].underlineThickness = 50
    builder.setupMaxp()
    # Enable smart dropout for small sizes without requiring a platform font hinter.
    prep = newTable("prep")
    prep.program = Program()
    prep.program.fromBytecode(bytes.fromhex("B8 01 FF 85 B0 04 8D"))
    builder.font["prep"] = prep
    builder.font["maxp"].maxStackElements = 2
    builder.setupHead()
    # Font timestamps use seconds since 1904-01-01. Fix them for repeatable builds.
    builder.font["head"].created = 2082844800
    builder.font["head"].modified = 2082844800
    builder.font["head"].fontRevision = 0.2
    builder.font.recalcTimestamp = False
    builder.save(ttf_path)
    font = TTFont(ttf_path, recalcTimestamp=False)
    font.flavor = "woff2"
    font.save(woff2_path)
    font.close()
    return ttf_path, woff2_path
