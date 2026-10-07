"""Exercise the generated outline in independent text shaping and rasterization engines."""

from pathlib import Path

import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from handfont.font import build_font
from handfont.manifest import GlyphSpec, Manifest


def test_counter_survives_font_rasterization_and_harfbuzz(tmp_path: Path) -> None:
    mask = np.zeros((80, 60), dtype=np.uint8)
    mask[3:77, 3:57] = 255
    mask[15:65, 15:45] = 0
    manifest = Manifest(60, (GlyphSpec("O", (0, 0, 60, 80), 650, 0),), {})
    ttf, woff2 = build_font(manifest, {"O": mask}, tmp_path, "Ring Hand")
    face = hb.Face(ttf.read_bytes())
    font = hb.Font(face)
    buffer = hb.Buffer()
    buffer.add_str("O O")
    buffer.guess_segment_properties()
    hb.shape(font, buffer)
    assert len(buffer.glyph_infos) == 3
    assert all(info.codepoint != 0 for info in buffer.glyph_infos)
    assert all(position.x_advance > 0 for position in buffer.glyph_positions)
    with TTFont(ttf) as installable, TTFont(woff2) as web:
        assert installable.getBestCmap() == web.getBestCmap()
        assert installable["hmtx"].metrics == web["hmtx"].metrics
    raster_font = ImageFont.truetype(str(ttf), 160)
    image = Image.new("L", (220, 200))
    ImageDraw.Draw(image).text((10, 10), "O", font=raster_font, fill=255, anchor="lt")
    bbox = image.getbbox()
    assert bbox is not None
    left, top, right, bottom = bbox
    assert image.getpixel(((left + right) // 2, (top + bottom) // 2)) == 0
    assert np.count_nonzero(np.asarray(image)) > 200
