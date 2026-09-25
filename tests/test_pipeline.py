"""Behavioral checks using a generated, non-private handwriting specimen."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

from lensa_hand.manifest import load_manifest
from lensa_hand.pipeline import build_project, validate_font
from lensa_hand.tracing import trace_glyphs


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


@pytest.fixture
def specimen(tmp_path: Path) -> tuple[Path, Path]:
    image = Image.new("RGB", (200, 90), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 13, 50, 52), outline="black", width=5)
    draw.ellipse((87, 11, 94, 18), fill="black")
    draw.line((91, 28, 91, 53), fill="black", width=5)
    image_path = tmp_path / "source.png"
    image.save(image_path)
    manifest_path = tmp_path / "alphabet.json"
    manifest_path.write_text(
        json.dumps(
            {
                "coordinate_width": 200,
                "glyphs": [
                    {"character": "o", "box": [5, 5, 59, 62], "height": 430, "bottom": 0},
                    {"character": "i", "box": [78, 5, 105, 62], "height": 610, "bottom": 0},
                ],
                "aliases": {"0": "o", "\u00a0": " "},
            }
        ),
        encoding="utf-8",
    )
    return image_path, manifest_path


def test_trace_preserves_counter_and_separate_dot(specimen: tuple[Path, Path]) -> None:
    image_path, manifest_path = specimen
    glyphs = trace_glyphs(image_path, load_manifest(manifest_path))
    ring = glyphs["o"]
    assert ring[ring.shape[0] // 2, ring.shape[1] // 2] == 0
    count, _ = cv2.connectedComponents(glyphs["i"])
    assert count == 3  # Background, dot, and stem.


def test_build_round_trip_and_repeatability(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image_path, manifest_path = specimen
    result = build_project(image_path, manifest_path, tmp_path / "output")
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
        assert cmap[ord("0")] == cmap[ord("o")]
        assert cmap[160] == cmap[32] == "space"
        assert ttf["hmtx"]["space"][0] > 0
        assert ttf["glyf"][cmap[ord("i")]].numberOfContours == 2
        assert ttf["glyf"][cmap[ord("o")]].numberOfContours == 2
        assert all(advance > 0 for advance, _ in ttf["hmtx"].metrics.values())
        areas = sorted(contour_areas(ttf, cmap[ord("o")]), key=abs, reverse=True)
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
    first_ttf = result.ttf.read_bytes()
    first_zip = result.archive.read_bytes()
    build_project(image_path, manifest_path, tmp_path / "output")
    assert result.ttf.read_bytes() == first_ttf
    assert result.archive.read_bytes() == first_zip


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
