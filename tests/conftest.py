"""Shared fixtures built from generated, non-private handwriting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def specimen(tmp_path: Path) -> tuple[Path, Path]:
    """A synthetic sheet with a ring for 'o' and a dotted stem for 'i', plus its manifest."""
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
                "aliases": {"0": "o", " ": " "},
            }
        ),
        encoding="utf-8",
    )
    return image_path, manifest_path
