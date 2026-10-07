"""Find photographed template pages, straighten them and measure what was written."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np

from .manifest import Box, GlyphSpec, Manifest
from .template import MARKER_DICTIONARY, MARKERS_PER_PAGE, Layout
from .tracing import Cell, load_image, trace_cells

X_HEIGHT_UNITS = 430
X_LETTERS = frozenset("acemnorsuvwxz")
BELOW_BASELINE = frozenset("gjpqy,;")  # characters that are meant to hang under the line
BASELINE_SNAP = 40  # font units; smaller wobble is treated as sitting on the baseline
MIN_INK_PIXELS = 120  # anything smaller in a cell is a stray mark, not a character
AUTO_ALIASES = {
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "–": "-",
    "—": "-",
    " ": " ",
}


@dataclass(frozen=True)
class CapturedPage:
    page: int
    image: np.ndarray
    photo: Path
    sheet_width: int  # how wide the sheet was in the photo, in photo pixels


@dataclass(frozen=True)
class Capture:
    manifest: Manifest
    masks: dict[str, np.ndarray]
    sheet: np.ndarray
    skipped: tuple[str, ...] = ()
    missing_pages: tuple[int, ...] = ()
    clipped: tuple[str, ...] = ()


def find_markers(rgb: np.ndarray) -> dict[int, np.ndarray]:
    """Corner markers visible in a photograph, keyed by marker id."""
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(MARKER_DICTIONARY), cv2.aruco.DetectorParameters()
    )
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    if ids is None:
        return {}
    return {
        int(marker_id): marker.reshape(4, 2)
        for marker_id, marker in zip(ids.ravel(), corners, strict=True)
    }


def detect_page(found: dict[int, np.ndarray]) -> int | None:
    """The template page whose four markers are all visible, or None."""
    for page in sorted({marker_id // MARKERS_PER_PAGE for marker_id in found}):
        if all(page * MARKERS_PER_PAGE + corner in found for corner in range(MARKERS_PER_PAGE)):
            return page
    return None


def capture_page(photo: Path, layout: Layout, rgb: np.ndarray | None = None) -> CapturedPage:
    """Locate the corner markers in a photograph and warp the page to template geometry."""
    if rgb is None:
        rgb = load_image(photo)
    found = find_markers(rgb)
    if not found:
        raise ValueError(
            f"No template markers found in {photo.name}; photograph the printed sheet flat"
            " with all four corner squares in view"
        )
    page = detect_page(found)
    if page is None:
        candidates = {marker_id // MARKERS_PER_PAGE for marker_id in found}
        page = max(candidates, key=lambda c: sum(1 for i in found if i // MARKERS_PER_PAGE == c))
        present = sum(1 for i in layout.marker_ids(page) if i in found)
        raise ValueError(
            f"Found {present} of 4 corner markers for page {page + 1} in {photo.name};"
            " retake the photo with the whole sheet in view and in focus"
        )
    needed = layout.marker_ids(page)
    source = np.concatenate([found[marker_id] for marker_id in needed]).astype(np.float32)
    target = np.array(
        [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)] for x0, y0, x1, y1 in layout.marker_boxes()],
        dtype=np.float32,
    ).reshape(-1, 2)
    homography, _ = cv2.findHomography(source, target, cv2.RANSAC, 3.0)
    if homography is None:
        raise ValueError(
            f"Could not straighten {photo.name}; retake it with the whole sheet in view"
        )
    image = cv2.warpPerspective(
        rgb,
        homography,
        layout.size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    centres = [found[marker_id].mean(axis=0) for marker_id in needed]
    sheet_width = int(round(float(np.linalg.norm(centres[1] - centres[0]))))
    return CapturedPage(page, image, Path(photo), sheet_width)


def derive_glyphs(
    cells: dict[str, Cell],
    boxes: dict[str, Box],
    baselines: dict[str, float],
    characters: str,
    *,
    remove_shift: bool,
) -> tuple[list[GlyphSpec], dict[str, np.ndarray]]:
    """Turn traced cells into glyph specifications with heights and baseline offsets.

    ``boxes`` are the crop boxes the cells were traced from; they go into the manifest
    unchanged so a hand-edited rebuild traces exactly what the automatic one did.

    Sizes are normalised so the writer's own x-height, the median height of the x-height
    letters, becomes 430 units; capitals, ascenders and descenders keep their real
    proportions. ``baselines`` gives the baseline's pixel row for each character. With
    ``remove_shift`` a consistent offset from that line (a writer who sits everything a
    little above a printed tick) is removed first. Small wobble is snapped so letters
    sit on the line.
    """
    heights = {character: box[3] - box[1] for character, (_, box) in cells.items()}
    offsets = {character: baselines[character] - box[3] for character, (_, box) in cells.items()}
    sitting = [offsets[c] for c in cells if c.isalnum() and c not in BELOW_BASELINE]
    shift = median(sitting) if remove_shift and len(sitting) >= 3 else 0
    x_samples = [heights[c] for c in cells if c in X_LETTERS]
    if len(x_samples) >= 3:
        x_height_px = median(x_samples)
    else:
        x_height_px = median(heights.values()) * 0.65 if heights else X_HEIGHT_UNITS
    scale = X_HEIGHT_UNITS / max(1.0, float(x_height_px))
    glyphs: list[GlyphSpec] = []
    masks: dict[str, np.ndarray] = {}
    for character in characters:
        if character not in cells:
            continue
        height = min(2000, max(1, round(heights[character] * scale)))
        bottom = round((offsets[character] - shift) * scale)
        if abs(bottom) <= BASELINE_SNAP:
            bottom = 0
        bottom = min(1500, max(-1000, bottom))
        glyphs.append(GlyphSpec(character, boxes[character], height, bottom))
        masks[character] = cells[character][0]
    return glyphs, masks


def auto_aliases(masks: dict[str, np.ndarray]) -> dict[str, str]:
    """Map typographic quotes and dashes onto written plain forms, unless written themselves."""
    return {
        alias: source
        for alias, source in AUTO_ALIASES.items()
        if alias not in masks and (source == " " or source in masks)
    }


def measure(pages: list[CapturedPage], characters: str, layout: Layout) -> Capture:
    """Trace every written template cell and derive the glyph specifications."""
    layout_pages = layout.pages(characters)
    by_page: dict[int, CapturedPage] = {}
    for captured in pages:
        if captured.page >= len(layout_pages):
            raise ValueError(
                f"{captured.photo.name} shows template page {captured.page + 1}, but this"
                f" character set has only {len(layout_pages)} page(s)"
            )
        if captured.page in by_page:
            raise ValueError(
                f"{captured.photo.name} and {by_page[captured.page].photo.name} both show"
                f" page {captured.page + 1}"
            )
        by_page[captured.page] = captured
    order = sorted(by_page)
    sheet = np.vstack([by_page[page].image for page in order])
    page_height = layout.size[1]
    boxes: dict[str, Box] = {}
    baselines: dict[str, float] = {}
    for stack_index, page in enumerate(order):
        offset = stack_index * page_height
        for cell, character in enumerate(layout_pages[page]):
            x0, y0, x1, y1 = layout.crop_box(cell)
            boxes[character] = (x0, y0 + offset, x1, y1 + offset)
            baselines[character] = layout.baseline_y(cell) + offset
    cells = trace_cells(sheet, boxes, min_ink=MIN_INK_PIXELS)
    written = {character: cell for character, cell in cells.items() if cell is not None}
    if not written:
        raise ValueError("No handwriting was found in any template cell")
    glyphs, masks = derive_glyphs(written, boxes, baselines, characters, remove_shift=True)
    skipped = tuple(c for c in characters if c in boxes and c not in written)
    missing_pages = tuple(page + 1 for page in range(len(layout_pages)) if page not in by_page)
    clipped = tuple(c for c in characters if c in written and _touches(written[c][1], boxes[c]))
    manifest = Manifest(layout.size[0], tuple(glyphs), auto_aliases(masks))
    return Capture(manifest, masks, sheet, skipped, missing_pages, clipped)


def _touches(ink: Box, crop: Box) -> bool:
    """Ink reaching the crop edge means the character ran out of its box."""
    return ink[0] <= crop[0] or ink[1] <= crop[1] or ink[2] >= crop[2] or ink[3] >= crop[3]


def resolution_note(page: CapturedPage, layout: Layout) -> str | None:
    """A warning when the sheet was photographed too small for crisp outlines."""
    span_mm = layout.page_width - 2 * layout.marker_inset - layout.marker
    pixels_per_mm = page.sheet_width / span_mm
    if pixels_per_mm >= 5:
        return None
    return (
        f"{page.photo.name} is low resolution ({pixels_per_mm:.1f} px/mm across the sheet);"
        " fill the frame with the sheet for crisper outlines"
    )
