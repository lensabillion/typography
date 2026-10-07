"""End to end: print a template, write on it with a stock font, photograph it, build a font."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from handfont.capture import capture_page
from handfont.cli import main
from handfont.manifest import load_manifest
from handfont.pipeline import BuildResult, build_from_template, build_project
from handfont.template import DEFAULT_CHARACTERS, Layout, render_page, write_template

EXTRA = "áéíóúñçüàè"  # pushes the default set onto a second page


def fill_in(page: Image.Image, characters: str, layout: Layout, skip: str = "") -> Image.Image:
    """Write each character into its cell with a stock font, baseline on the printed tick."""
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=105)
    for cell, character in enumerate(characters):
        if character in skip:
            continue
        x0, _, x1, _ = layout.writing_area(cell)
        draw.text(
            ((x0 + x1) // 2, layout.baseline_y(cell)),
            character,
            font=font,
            fill="black",
            anchor="ms",
        )
    return page


def photograph(page: Image.Image, path: Path, seed: int = 1) -> Path:
    """Simulate a phone photo: perspective, lower resolution, uneven light, blur and JPEG."""
    rgb = np.asarray(page)
    height, width = rgb.shape[:2]
    canvas = (round(width * 0.6), round(height * 0.6))
    rng = np.random.default_rng(seed)
    source = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    margin = np.float32([[40, 40], [-40, 40], [-40, -40], [40, -40]])
    target = np.float32([[0, 0], [canvas[0], 0], canvas, [0, canvas[1]]]) + margin
    target += rng.uniform(-25, 25, size=(4, 2)).astype(np.float32)
    photo = cv2.warpPerspective(
        rgb, cv2.getPerspectiveTransform(source, target), canvas, borderValue=(200, 195, 185)
    )
    gradient = np.linspace(0.82, 1.0, canvas[0], dtype=np.float32)
    photo = np.clip(photo * gradient[None, :, None], 0, 255).astype(np.uint8)
    photo = cv2.GaussianBlur(photo, (0, 0), 0.8)
    Image.fromarray(photo).save(path, quality=85)
    return path


@pytest.fixture(scope="module")
def default_photo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    layout = Layout()
    page = fill_in(
        render_page(layout, DEFAULT_CHARACTERS, 0, 1, "t"), DEFAULT_CHARACTERS, layout, "Q#"
    )
    return photograph(page, tmp_path_factory.mktemp("photo") / "sheet.jpg")


@pytest.fixture(scope="module")
def default_build(default_photo: Path, tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    return build_from_template(
        [default_photo], tmp_path_factory.mktemp("build") / "out", "Test Hand"
    )


@pytest.fixture(scope="module")
def two_page_photos(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    layout = Layout()
    pages = layout.pages(DEFAULT_CHARACTERS + EXTRA)
    assert len(pages) == 2
    directory = tmp_path_factory.mktemp("pages")
    photos = []
    for index, characters in enumerate(pages):
        page = fill_in(render_page(layout, characters, index, 2, "t"), characters, layout)
        photos.append(photograph(page, directory / f"page{index + 1}.jpg", seed=index + 5))
    return photos


def test_template_round_trip_builds_the_repertoire(default_build: BuildResult) -> None:
    result = default_build
    assert result.skipped == ("Q", "#")
    assert result.glyph_count == len(DEFAULT_CHARACTERS) - 2
    assert result.missing_pages == ()
    spec = {glyph.character: glyph for glyph in load_manifest(result.manifest).glyphs}
    assert 380 <= spec["x"].height <= 480  # the writer's x-height becomes about 430 units
    assert spec["H"].height > spec["x"].height * 1.2  # capitals keep their real proportion
    assert spec["g"].bottom < -40  # descenders hang below the line
    assert spec["a"].bottom == 0 == spec["H"].bottom  # baseline letters sit on it
    assert spec["'"].bottom > 200  # floating marks keep their position
    with TTFont(result.ttf) as font:
        cmap = font.getBestCmap()
        assert ord("Q") not in cmap and ord("#") not in cmap
        assert cmap[ord("“")] == cmap[ord('"')] and cmap[ord("—")] == cmap[ord("-")]
        assert font["name"].getDebugName(1) == "Test Hand"
        glyf = font["glyf"]
        drawn = [name for name in font.getGlyphOrder() if glyf[name].numberOfContours > 0]
        deepest = -min(glyf[name].yMin for name in drawn)
        assert deepest <= font["OS/2"].usWinDescent <= 2 * deepest  # FontBakery's clipping rule
    assert "Not written on the sheet: Q #" in result.tester.read_text(encoding="utf-8")
    assert "Q #" in result.readme.read_text(encoding="utf-8")


def test_derived_crop_map_reproduces_the_font(default_build: BuildResult, tmp_path: Path) -> None:
    again = build_project(
        default_build.sheet, default_build.manifest, tmp_path / "again", "Test Hand"
    )
    assert again.ttf.read_bytes() == default_build.ttf.read_bytes()


def test_cli_builds_from_a_photo(
    default_photo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli"
    assert (
        main(
            [
                "build",
                "--photo",
                str(default_photo),
                "--family",
                "CLI Hand",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Empty cells skipped: Q #" in text and "crop map" in text
    assert (output / "CLIHand-Regular.woff2").is_file() and (output / "manifest.json").is_file()


def test_two_page_sets_join_in_any_order(two_page_photos: list[Path], tmp_path: Path) -> None:
    characters = DEFAULT_CHARACTERS + EXTRA
    result = build_from_template(two_page_photos[::-1], tmp_path / "out", "Two Pages", characters)
    assert result.glyph_count == len(characters) and result.skipped == ()
    assert result.clipped == ()  # accented capitals fit the box
    with TTFont(result.ttf) as font:
        assert ord("ñ") in font.getBestCmap()


def test_missing_page_is_reported(two_page_photos: list[Path], tmp_path: Path) -> None:
    characters = DEFAULT_CHARACTERS + EXTRA
    result = build_from_template(two_page_photos[:1], tmp_path / "out", "One Page", characters)
    assert result.missing_pages == (2,)
    assert result.glyph_count == Layout().cells_per_page
    with pytest.raises(ValueError, match="both show page 1"):
        build_from_template(two_page_photos[:1] * 2, tmp_path / "dup", "Dup", characters)
    with pytest.raises(ValueError, match="only 1 page"):
        build_from_template(two_page_photos[1:], tmp_path / "extra", "Extra", DEFAULT_CHARACTERS)


def test_unusable_photos_fail_clearly(tmp_path: Path) -> None:
    blank = tmp_path / "blank.jpg"
    Image.new("RGB", (800, 1000), "white").save(blank)
    with pytest.raises(ValueError, match="No template markers"):
        capture_page(blank, Layout())
    layout = Layout()
    page = render_page(layout, "abc", 0, 1, "t")
    cut = tmp_path / "cut.png"
    page.crop((0, 0, page.width - 400, page.height)).save(cut)  # right-hand markers lost
    with pytest.raises(ValueError, match="2 of 4 corner markers"):
        capture_page(cut, layout)


def test_write_template_outputs_pdf_and_pages(tmp_path: Path) -> None:
    paths = write_template(tmp_path / "t", "abc", "Mini")
    assert [path.name for path in paths] == ["template.pdf", "template-page-1.png"]
    with Image.open(paths[1]) as page:
        assert page.size == Layout().size
    with pytest.raises(ValueError, match="repeats"):
        write_template(tmp_path / "u", "aab")
    with pytest.raises(ValueError, match="spaces"):
        write_template(tmp_path / "v", "a b")
    with pytest.raises(ValueError, match="empty"):
        write_template(tmp_path / "w", "")


def test_upside_down_photo_still_builds(default_photo: Path, tmp_path: Path) -> None:
    flipped = tmp_path / "flipped.jpg"
    with Image.open(default_photo) as photo:
        photo.rotate(180).save(flipped, quality=85)
    result = build_from_template([flipped], tmp_path / "out", "Flipped")
    assert result.glyph_count == len(DEFAULT_CHARACTERS) - 2 and result.skipped == ("Q", "#")


def test_written_curly_quotes_are_glyphs_not_aliases(tmp_path: Path) -> None:
    characters = 'ab"\u201c\u201dcd-\u2013'
    layout = Layout()
    page = fill_in(render_page(layout, characters, 0, 1, "t"), characters, layout)
    photo = photograph(page, tmp_path / "quotes.jpg", seed=9)
    result = build_from_template([photo], tmp_path / "out", "Quotes", characters)
    assert result.glyph_count == len(characters)
    with TTFont(result.ttf) as font:
        cmap = font.getBestCmap()
        assert cmap[ord("\u201c")] != cmap[ord('"')] and cmap[ord("\u2013")] != cmap[ord("-")]
        assert cmap[ord("\u2014")] == cmap[ord("-")]  # the unwritten em dash still maps
        assert ord("\u2018") not in cmap  # no plain apostrophe was written to alias it


def test_ink_past_the_box_edge_is_reported(tmp_path: Path) -> None:
    layout = Layout()
    page = fill_in(render_page(layout, "abl", 0, 1, "t"), "ab", layout)
    draw = ImageDraw.Draw(page)
    x0, y0, x1, _ = layout.writing_area(2)
    draw.line(
        ((x0 + x1) // 2, y0 - 40, (x0 + x1) // 2, layout.baseline_y(2)), fill="black", width=12
    )
    photo = photograph(page, tmp_path / "tall.jpg", seed=11)
    result = build_from_template([photo], tmp_path / "out", "Tall", "abl")
    assert result.clipped == ("l",) and result.skipped == ()
    assert "clipped" in result.build_info.read_text(encoding="utf-8")
