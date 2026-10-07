"""Behavioral checks using a generated, non-private handwriting specimen."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from handfont.font import build_font
from handfont.manifest import load_manifest
from handfont.pipeline import build_project, validate_font
from handfont.tracing import trace_glyphs


def contour_areas(font: TTFont, glyph_name: str) -> list[float]:
    drawing = RecordingPen()
    font["glyf"][glyph_name].draw(drawing, font["glyf"])
    areas = []
    pen = AreaPen()
    for operation, points in drawing.value:
        getattr(pen, operation)(*points)
        if operation == "closePath":
            areas.append(pen.value)
            pen = AreaPen()
    return areas


def test_trace_preserves_counter_and_separate_dot(specimen: tuple[Path, Path]) -> None:
    image_path, manifest_path = specimen
    glyphs = trace_glyphs(image_path, load_manifest(manifest_path))
    ring = glyphs["o"]
    assert ring[ring.shape[0] // 2, ring.shape[1] // 2] == 0
    count, _ = cv2.connectedComponents(glyphs["i"])
    assert count == 3  # Background, dot, and stem.


def test_build_round_trip_and_repeatability(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image_path, manifest_path = specimen
    result = build_project(image_path, manifest_path, tmp_path / "output", "Lensa Hand")
    assert result.glyph_count == 2
    assert all(
        path.is_file()
        for path in (
            result.ttf,
            result.woff2,
            result.css,
            result.preview,
            result.tracing_sheet,
            result.tester,
            result.readme,
            result.archive,
        )
    )
    assert validate_font(result.ttf, manifest_path)["characters"] == 5
    with TTFont(result.ttf) as ttf, TTFont(result.woff2) as woff2:
        assert ttf.getBestCmap() == woff2.getBestCmap()
        cmap = ttf.getBestCmap()
        assert cmap[ord("o")] == "o" and cmap[ord("i")] == "i"  # Adobe Glyph List names.
        assert cmap[ord("0")] == cmap[ord("o")]
        assert cmap[160] == cmap[32] == "space"
        assert ttf["hmtx"]["space"][0] > 0
        assert ttf["glyf"]["i"].numberOfContours == 2
        assert ttf["glyf"]["o"].numberOfContours == 2
        assert all(advance > 0 for advance, _ in ttf["hmtx"].metrics.values())
        areas = sorted(contour_areas(ttf, "o"), key=abs, reverse=True)
        assert areas[0] < 0 < areas[1]
        missing_areas = sorted(contour_areas(ttf, ".notdef"), key=abs, reverse=True)
        assert missing_areas[0] < 0 < missing_areas[1]
        assert ttf["OS/2"].fsType == 0
        top = ttf["OS/2"].usWinAscent
        bottom = -ttf["OS/2"].usWinDescent
        assert all(
            bottom <= glyph.yMin <= glyph.yMax <= top
            for glyph in ttf["glyf"].glyphs.values()
            if getattr(glyph, "numberOfContours", 0) > 0
        )
        # Side bearings equal the outline bounds, which fontTools confirms by
        # keeping head.flags bit 1 ("left sidebearing point at x=0") set.
        assert ttf["head"].flags & 0x2
        assert all(ttf["hmtx"][name][1] == ttf["glyf"][name].xMin for name in ("o", "i", ".notdef"))
        assert ttf["gasp"].gaspRange == {7: 10, 0xFFFF: 15}
        assert ttf["OS/2"].panose.bFamilyType == 3
        assert (ttf["OS/2"].sxHeight, ttf["OS/2"].sCapHeight) == (430, 650)
        assert ttf["name"].getDebugName(5) == "Version 1.000"
        assert round(ttf["head"].fontRevision, 3) == 1.0
    first_ttf = result.ttf.read_bytes()
    first_zip = result.archive.read_bytes()
    build_project(image_path, manifest_path, tmp_path / "output", "Lensa Hand")
    assert result.ttf.read_bytes() == first_ttf
    assert result.archive.read_bytes() == first_zip


def test_manifest_metrics_control_spacing(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image_path, manifest_path = specimen
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["metrics"] = {"sidebearing": 30, "word_space": 250}
    data["glyphs"][0].update({"left": 10, "right": 20})
    spaced = tmp_path / "spaced.json"
    spaced.write_text(json.dumps(data), encoding="utf-8")
    manifest = load_manifest(spaced)
    ttf, _ = build_font(manifest, trace_glyphs(image_path, manifest), tmp_path / "spaced", "Spaced")
    with TTFont(ttf) as font:
        hmtx, glyf = font["hmtx"], font["glyf"]
        assert tuple(hmtx["space"]) == (250, 0)
        assert hmtx["o"][1] == glyf["o"].xMin == 10
        assert hmtx["o"][0] == glyf["o"].xMax + 20
        assert hmtx["i"][1] == glyf["i"].xMin == 30
        assert hmtx["i"][0] == glyf["i"].xMax + 30


def test_validate_font_rejects_corrupted_fonts(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image_path, manifest_path = specimen
    manifest = load_manifest(manifest_path)
    ttf, _ = build_font(manifest, trace_glyphs(image_path, manifest), tmp_path / "good", "Good")

    def tampered(label: str, mutate) -> Path:
        with TTFont(ttf, recalcTimestamp=False) as font:
            mutate(font)
            path = tmp_path / f"{label}.ttf"
            font.save(path)
        return path

    def zero_advance(font: TTFont) -> None:
        font["hmtx"].metrics["o"] = (0, font["hmtx"]["o"][1])

    def shifted_bearing(font: TTFont) -> None:
        advance, bearing = font["hmtx"]["o"]
        font["hmtx"].metrics["o"] = (advance, bearing + 7)

    def drop_table(font: TTFont) -> None:
        del font["OS/2"]

    def restrict_embedding(font: TTFont) -> None:
        font["OS/2"].fsType = 2

    def odd_units(font: TTFont) -> None:
        font["head"].unitsPerEm = 2048

    cases = [
        ("advance", zero_advance, "nonpositive glyph advance"),
        ("bearing", shifted_bearing, "left side bearing disagrees"),
        ("tables", drop_table, "lacks required tables: OS/2"),
        ("embedding", restrict_embedding, "embedding"),
        ("units", odd_units, "units per em"),
    ]
    for label, mutate, message in cases:
        with pytest.raises(ValueError, match=message):
            validate_font(tampered(label, mutate))
    other = tmp_path / "other.json"
    other.write_text(
        json.dumps(
            {
                "coordinate_width": 10,
                "glyphs": [{"character": "z", "box": [0, 0, 5, 5], "height": 430, "bottom": 0}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"U\+007A"):
        validate_font(ttf, other)


def test_bad_crop_reports_character(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image_path, manifest_path = specimen
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["glyphs"][1]["box"] = [150, 5, 190, 62]
    bad_manifest = tmp_path / "bad.json"
    bad_manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="'i'"):
        trace_glyphs(image_path, load_manifest(bad_manifest))


def test_bad_manifest_fails_early(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"coordinate_width":1373,"glyphs":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_manifest(path)


def test_manifest_version_sets_font_revision(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image_path, manifest_path = specimen
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["version"] = "2.15"
    versioned = tmp_path / "versioned.json"
    versioned.write_text(json.dumps(data), encoding="utf-8")
    manifest = load_manifest(versioned)
    ttf, _ = build_font(manifest, trace_glyphs(image_path, manifest), tmp_path / "v", "Versioned")
    with TTFont(ttf) as font:
        assert font["name"].getDebugName(5) == "Version 2.150"
        assert font["name"].getDebugName(3) == "Versioned-Regular-2.15"
        assert round(font["head"].fontRevision, 3) == 2.15
