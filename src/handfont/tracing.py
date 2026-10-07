"""Convert the photographed ink inside crop boxes to binary masks."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

from .manifest import Box, Manifest

Cell = tuple[np.ndarray, Box]

register_heif_opener()  # iPhone photos arrive as HEIC.


def load_image(source: Path) -> np.ndarray:
    """Read a photograph as an RGB array."""
    try:
        with Image.open(source) as image:
            return np.asarray(image.convert("RGB"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot open source image {source}: {exc}") from exc


def ink_mask(rgb: np.ndarray) -> np.ndarray:
    """Mark ink: whatever is darker than the locally blurred paper.

    Comparing against the local background tolerates uneven lighting and shadows
    across a phone photograph, and works for any pen colour darker than the paper.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    background = cv2.GaussianBlur(gray, (0, 0), 9)
    difference = background.astype(np.float32) - gray.astype(np.float32)
    mask = (difference > 7).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))


def trace_cells(
    rgb: np.ndarray, boxes: dict[str, Box], *, min_ink: int = 1
) -> dict[str, Cell | None]:
    """Return each character's tight ink mask and its bounds in image pixels.

    A box holding fewer than ``min_ink`` ink pixels maps to ``None``.
    """
    result: dict[str, Cell | None] = {}
    for character, (x1, y1, x2, y2) in boxes.items():
        if x1 < 0 or y1 < 0 or x2 > rgb.shape[1] or y2 > rgb.shape[0] or x2 <= x1 or y2 <= y1:
            raise ValueError(f"Crop for {character!r} lies outside the source image")
        mask = ink_mask(rgb[y1:y2, x1:x2])
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        clean = np.zeros_like(mask)
        if count > 1:
            largest = int(stats[1:, cv2.CC_STAT_AREA].max())
            for component in range(1, count):
                if stats[component, cv2.CC_STAT_AREA] >= max(8, largest * 0.025):
                    clean[labels == component] = 255
            clean = cv2.dilate(clean, np.ones((2, 2), np.uint8))
        rows, columns = np.where(clean > 0)
        if len(columns) < max(1, min_ink):
            result[character] = None
            continue
        top, bottom = int(rows.min()), int(rows.max()) + 1
        left, right = int(columns.min()), int(columns.max()) + 1
        result[character] = (
            clean[top:bottom, left:right],
            (x1 + left, y1 + top, x1 + right, y1 + bottom),
        )
    return result


def trace_glyphs(source: Path, manifest: Manifest) -> dict[str, np.ndarray]:
    """Trace every manifest glyph from a photograph whose crop boxes the manifest describes."""
    rgb = load_image(source)
    ratio = rgb.shape[1] / manifest.coordinate_width
    boxes: dict[str, Box] = {}
    for spec in manifest.glyphs:
        x1, y1, x2, y2 = (round(value * ratio) for value in spec.box)
        boxes[spec.character] = (x1, y1, x2, y2)
    glyphs: dict[str, np.ndarray] = {}
    for character, cell in trace_cells(rgb, boxes).items():
        if cell is None:
            raise ValueError(f"No ink found for {character!r}; check its crop")
        glyphs[character] = cell[0]
    return glyphs
