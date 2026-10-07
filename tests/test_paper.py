"""Plain paper: rows of characters photographed without the printed template."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from test_template import fill_in, photograph

from handfont.cli import main
from handfont.manifest import load_manifest
from handfont.pipeline import BuildResult, build_from_paper, build_from_photos, build_project
from handfont.template import DEFAULT_CHARACTERS, Layout, render_page

DESK = (120, 110, 100)


def write_rows(
    path: Path,
    characters: str,
    *,
    skip: str = "",
    ruled: bool = False,
    angle: float = 2.0,
    seed: int = 1,
) -> Path:
    """Write the rows with a stock font, then photograph the page slightly tilted on a desk."""
    columns = Layout().columns
    rows = [characters[start : start + columns] for start in range(0, len(characters), columns)]
    page = Image.new("RGB", (1700, 2300), "white")
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=72)
    rng = np.random.default_rng(seed)
    y = 260
    for row in rows:
        if ruled:
            draw.line((60, y + 2, 1640, y + 2), fill=(150, 185, 235), width=3)
        x = 180
        for character in row:
            if character not in skip:
                jitter = int(rng.integers(-12, 12))
                draw.text((x + jitter, y), character, font=font, fill=(25, 25, 45), anchor="ls")
            x += 150
        y += 185
    tilted = page.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=DESK)
    desk = Image.new("RGB", (tilted.width + 160, tilted.height + 160), DESK)
    desk.paste(tilted, (80, 80))
    desk.save(path, quality=88)
    return path


@pytest.fixture(scope="module")
def paper_photo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_rows(tmp_path_factory.mktemp("paper") / "rows.jpg", DEFAULT_CHARACTERS)


@pytest.fixture(scope="module")
def paper_build(paper_photo: Path, tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    return build_from_paper([paper_photo], tmp_path_factory.mktemp("build") / "out", "Paper Hand")


def test_rows_on_plain_paper_become_a_font(paper_build: BuildResult) -> None:
    result = paper_build
    assert result.mode == "paper" and result.glyph_count == len(DEFAULT_CHARACTERS)
    assert result.layout_check is not None and result.layout_check.is_file()
    spec = {glyph.character: glyph for glyph in load_manifest(result.manifest).glyphs}
    assert 380 <= spec["x"].height <= 480
    assert spec["H"].height > spec["x"].height * 1.2
    assert spec["g"].bottom < -40 and spec["a"].bottom == 0 == spec["H"].bottom
    with TTFont(result.ttf) as font:
        glyf = font["glyf"]
        # Multi-part characters were joined: dots, second strokes and crossing parts.
        for name in ("i", "j", "quotedbl", "colon", "semicolon", "equal", "exclam", "question"):
            assert glyf[name].numberOfContours == 2, name
        assert glyf["percent"].numberOfContours >= 3
        assert all(advance < 1500 for advance, _ in font["hmtx"].metrics.values())


def test_derived_crop_map_reproduces_the_paper_font(
    paper_build: BuildResult, tmp_path: Path
) -> None:
    again = build_project(paper_build.sheet, paper_build.manifest, tmp_path / "again", "Paper Hand")
    assert again.ttf.read_bytes() == paper_build.ttf.read_bytes()


def test_ruled_paper_lines_are_removed(tmp_path: Path) -> None:
    photo = write_rows(tmp_path / "ruled.jpg", DEFAULT_CHARACTERS, ruled=True, angle=-1.5, seed=4)
    result = build_from_paper([photo], tmp_path / "out", "Ruled Hand")
    assert result.glyph_count == len(DEFAULT_CHARACTERS)
    spec = {glyph.character: glyph for glyph in load_manifest(result.manifest).glyphs}
    assert spec["a"].bottom == 0 and spec["g"].bottom < -40
    with TTFont(result.ttf) as font:
        assert all(advance < 1500 for advance, _ in font["hmtx"].metrics.values())


def test_wrong_row_length_is_explained_with_a_picture(tmp_path: Path) -> None:
    photo = write_rows(tmp_path / "short.jpg", DEFAULT_CHARACTERS, skip="k")
    with pytest.raises(ValueError, match=r"Row 2 holds 8 characters but should hold 9"):
        build_from_paper([photo], tmp_path / "out", "Short Hand")
    assert (tmp_path / "out" / "layout-check.png").is_file()


def test_photos_are_routed_by_their_markers(paper_photo: Path, tmp_path: Path) -> None:
    result = build_from_photos([paper_photo], tmp_path / "paper", "Routed", DEFAULT_CHARACTERS)
    assert result.mode == "paper"
    layout = Layout()
    page = fill_in(render_page(layout, "abc", 0, 1, "t"), "abc", layout)
    template_photo = photograph(page, tmp_path / "template.jpg")
    assert build_from_photos([template_photo], tmp_path / "t", "Routed", "abc").mode == "template"
    with pytest.raises(ValueError, match="separately"):
        build_from_photos([paper_photo, template_photo], tmp_path / "mixed", "Mixed")


def test_cli_reports_the_plain_paper_build(
    paper_photo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli"
    args = ["build", "--photo", str(paper_photo), "--family", "CLI Paper", "--output", str(output)]
    assert main(args) == 0
    text = capsys.readouterr().out
    assert "rows on plain paper" in text and "layout-check.png" in text
