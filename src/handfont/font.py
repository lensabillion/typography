"""Draw TrueType outlines and write installable and web font files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import potrace
from fontTools.agl import UV2AGL
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.arrayTools import calcIntBounds
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from fontTools.ttLib.tables.ttProgram import Program

from .manifest import Manifest

# Rendering advice for rasterizers that honour the gasp table (Windows GDI and
# DirectWrite): grayscale with symmetric smoothing at tiny sizes, grid-fitting
# plus antialiasing everywhere else. Without this table Windows may draw an
# unhinted TrueType font aliased at some sizes.
GASP_RANGES = {7: 0x02 | 0x08, 0xFFFF: 0x01 | 0x02 | 0x04 | 0x08}


def font_stem(family: str) -> str:
    """Return the ASCII stem used for file and PostScript names, or raise for a bad family."""
    if not family.strip():
        raise ValueError("Font family must not be blank")
    if any(c in '"\\:#' or ord(c) < 32 for c in family):
        raise ValueError("Font family must not contain quotes, backslashes, colons or hash signs")
    stem = "".join(character for character in family if character.isascii() and character.isalnum())
    if not stem:
        raise ValueError("Font family must contain letters or numbers")
    if len(stem) > 55:
        raise ValueError("Font family is too long; keep it under 56 letters and digits")
    return stem


def _glyph_name(character: str) -> str:
    """Adobe Glyph List name when one exists, otherwise the uniXXXX convention."""
    code = ord(character)
    name = UV2AGL.get(code)
    if name is not None:
        return name
    return f"uni{code:04X}" if code <= 0xFFFF else f"u{code:06X}"


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


def _outline(mask: np.ndarray, height: int, bottom: int, left: int, right: int):
    rows = mask.shape[0]
    scale = height / rows
    pen = TTGlyphPen(None)
    # Potrace follows the pencil edge with cubic curves. FontTools converts those
    # curves to TrueType's quadratic outlines within one font unit of error.
    curves = potrace.Bitmap(255 - mask).trace(turdsize=1, alphamax=1.0)
    if not curves:
        raise ValueError("Traced glyph has no contours")

    def point(value):
        return (value.x * scale, (rows - value.y) * scale + bottom)

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
    glyph = pen.glyph()
    x_min, _, x_max, _ = calcIntBounds(glyph.coordinates)
    # Put the outline's left edge exactly on the left side bearing. The hmtx entry
    # then equals the glyph's xMin, so every rasterizer positions it the same way.
    glyph.coordinates.translate((left - x_min, 0))
    return glyph, (x_max - x_min + left + right, left)


def build_font(
    manifest: Manifest, glyphs: dict[str, np.ndarray], output: Path, family: str
) -> tuple[Path, Path]:
    stem = font_stem(family)
    output.mkdir(parents=True, exist_ok=True)
    ttf_path = output / f"{stem}-Regular.ttf"
    woff2_path = output / f"{stem}-Regular.woff2"
    version_name, revision = manifest.revision()
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
    metrics = {".notdef": (450, 50), "space": (manifest.word_space, 0)}
    for spec in manifest.glyphs:
        if spec.character not in glyphs:
            raise ValueError(f"Missing traced glyph {spec.character!r}")
        name = _glyph_name(spec.character)
        outlines[name], metrics[name] = _outline(
            glyphs[spec.character],
            spec.height,
            spec.bottom,
            manifest.left_bearing(spec),
            manifest.right_bearing(spec),
        )
    # Vertical metrics come from the drawn outlines, not the requested heights, so
    # a traced curve that overshoots its box can never be clipped.
    bounds = [
        calcIntBounds(glyph.coordinates)
        for glyph in outlines.values()
        if glyph.numberOfContours > 0
    ]
    bounds_top = max(box[3] for box in bounds)
    bounds_bottom = min(box[1] for box in bounds)
    ascent = max(1150, bounds_top + 25)
    descent = -max(300, -bounds_bottom + 25)
    # Windows clipping bounds: at least the outline extent, at most twice it (the
    # FontBakery sanity rule), and otherwise as generous as the line metrics above.
    win_ascent = max(bounds_top, min(ascent, 2 * bounds_top))
    win_descent = max(-bounds_bottom, min(max(350, -bounds_bottom + 25), -2 * bounds_bottom))
    heights = {spec.character: spec.height + spec.bottom for spec in manifest.glyphs}
    builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=0)
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{stem}-Regular-{manifest.version}",
            "fullName": f"{family} Regular",
            "psName": f"{stem}-Regular",
            "version": version_name,
        },
        mac=False,
    )
    builder.setupOS2(
        version=4,
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sTypoLineGap=0,
        usWinAscent=win_ascent,
        usWinDescent=win_descent,
        sxHeight=heights.get("x", 430),
        sCapHeight=heights.get("H", 650),
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
        panose=Panose(bFamilyType=3),  # PANOSE family kind 3: Latin hand written.
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
    gasp = newTable("gasp")
    gasp.version = 1
    gasp.gaspRange = dict(GASP_RANGES)
    builder.font["gasp"] = gasp
    builder.setupHead()
    # Font timestamps use seconds since 1904-01-01. Fix them for repeatable builds.
    builder.font["head"].created = 2082844800
    builder.font["head"].modified = 2082844800
    builder.font["head"].fontRevision = revision
    builder.font.recalcTimestamp = False
    builder.save(ttf_path)
    font = TTFont(ttf_path, recalcTimestamp=False)
    font.flavor = "woff2"
    font.save(woff2_path)
    font.close()
    return ttf_path, woff2_path
