"""Convert the photographed ink inside each manifest box to a binary mask."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .manifest import Manifest


def trace_glyphs(source: Path, manifest: Manifest) -> dict[str, np.ndarray]:
    try:
        with Image.open(source) as image:
            rgb = np.asarray(image.convert("RGB"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot open source image {source}: {exc}") from exc

    ratio = rgb.shape[1] / manifest.coordinate_width
    result: dict[str, np.ndarray] = {}
    for spec in manifest.glyphs:
        x1, y1, x2, y2 = (round(value * ratio) for value in spec.box)
        if x1 < 0 or y1 < 0 or x2 > rgb.shape[1] or y2 > rgb.shape[0] or x2 <= x1 or y2 <= y1:
            raise ValueError(f"Crop for {spec.character!r} lies outside the source image")
        crop = rgb[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        background = cv2.GaussianBlur(gray, (0, 0), 9)
        difference = background.astype(np.float32) - gray.astype(np.float32)
        mask = (difference > 7).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        if count <= 1:
            raise ValueError(f"No ink found for {spec.character!r}; check its crop")
        largest = int(stats[1:, cv2.CC_STAT_AREA].max())
        clean = np.zeros_like(mask)
        for component in range(1, count):
            if stats[component, cv2.CC_STAT_AREA] >= max(8, largest * 0.025):
                clean[labels == component] = 255
        clean = cv2.dilate(clean, np.ones((2, 2), np.uint8))
        rows, columns = np.where(clean > 0)
        if not len(columns):
            raise ValueError(f"No usable ink found for {spec.character!r}; check its crop")
        result[spec.character] = clean[
            rows.min() : rows.max() + 1, columns.min() : columns.max() + 1
        ]
    return result
