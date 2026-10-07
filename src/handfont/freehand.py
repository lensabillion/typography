"""Capture characters written on any paper, in rows, without the printed template."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np

from .capture import BELOW_BASELINE, MIN_INK_PIXELS, Capture, auto_aliases, derive_glyphs
from .manifest import Box, Manifest
from .tracing import ink_mask, load_image, trace_cells

# Punctuation that normally rests on the baseline; used with letters and digits to find
# each row's baseline when there is no printed one.
ROW_SITTERS = frozenset(".:!?@#$%&[]{}/\\|")
MAX_SKEW_DEGREES = 10


class LayoutError(ValueError):
    """Writing was found but could not be matched to the expected rows of characters."""

    def __init__(self, message: str, sheet: np.ndarray, boxes: list[Box]) -> None:
        super().__init__(message)
        self.sheet = sheet
        self.boxes = boxes


@dataclass(frozen=True)
class Band:
    top: int
    bottom: int

    @property
    def height(self) -> int:
        return self.bottom - self.top


def _rotate(image: np.ndarray, angle: float, fill: int | tuple[int, int, int]) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=fill)


def _skew_angle(mask: np.ndarray) -> float:
    """Rotation that makes the rows of writing horizontal, by the sharpest row profile."""
    scale = 600 / mask.shape[1]
    small = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    best, best_score = 0.0, -1.0
    for angle in np.arange(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES + 0.01, 0.5):
        rotated = _rotate(small, float(angle), 0)
        profile = (rotated > 0).sum(axis=1).astype(np.float64)
        score = float(np.sum(np.diff(profile) ** 2))
        if score > best_score:
            best, best_score = float(angle), score
    return best


def _line_band(
    gray: np.ndarray,
    mask: np.ndarray,
    run: tuple[int, int],
    thicken: tuple[int, int],
    window: tuple[int, int],
) -> np.ndarray:
    """Pixels of long straight runs of ink, minus any part that is not the line itself.

    Thickening the mask first lets a slightly wobbly line count as one run, and
    lengthening it bridges the short breaks that appear beside dark strokes crossing a
    faint line. A stroke lying on a ruled line (an underscore, the foot of a letter) is
    thicker than the line or darker than the printed ruling, and that part is kept.
    """
    thick = cv2.dilate(mask, np.ones(thicken, np.uint8))
    runs = cv2.morphologyEx(thick, cv2.MORPH_OPEN, np.ones(run, np.uint8))
    band = cv2.dilate(runs, np.ones((3, 3), np.uint8))
    if not band.any():
        return band
    inked = cv2.bitwise_and(mask, band)
    depth = cv2.boxFilter((inked > 0).astype(np.float32), -1, window, normalize=False)
    typical = float(np.median(depth[inked > 0]))
    line_gray = float(np.median(gray[inked > 0]))
    thicker = depth > typical + 2
    darker = (inked > 0) & (gray < line_gray - 40)
    heavy = (thicker | darker).astype(np.uint8) * 255
    return cv2.bitwise_and(band, cv2.bitwise_not(cv2.dilate(heavy, np.ones((3, 3), np.uint8))))


def _remove_lines(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Paint ruled lines and page edges out of the photograph so letters stand alone.

    Where a character crosses a line, the line is kept so the stroke stays continuous.
    """
    height, width = mask.shape
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    bridge = 2 * max(9, width // 120) + 1
    band = cv2.bitwise_or(
        _line_band(gray, mask, (1, max(50, width // 12)), (5, bridge), (1, 15)),
        _line_band(gray, mask, (max(50, height // 12), 1), (bridge, 5), (15, 1)),
    )
    if not band.any():
        return rgb, mask
    bodies = cv2.bitwise_and(mask, cv2.bitwise_not(band))
    crossing = cv2.dilate(bodies, np.ones((9, 9), np.uint8))
    lines = cv2.bitwise_and(band, cv2.bitwise_not(crossing))
    paper = cv2.medianBlur(rgb, 21)
    cleaned = rgb.copy()
    cleaned[lines > 0] = paper[lines > 0]
    return cleaned, cv2.bitwise_and(mask, cv2.bitwise_not(lines))


def _paper_mask(rgb: np.ndarray) -> np.ndarray:
    """The sheet of paper: the largest bright region, shrunk so its edges are excluded."""
    height, width = rgb.shape[:2]
    scale = min(1.0, 800 / width)
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (0, 0), 2)
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(bright)
    if count <= 1:
        return np.full((height, width), 255, np.uint8)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    points = cv2.findNonZero((labels == largest).astype(np.uint8))
    hull = cv2.convexHull(points)  # the paper is a rectangle, so its hull is the whole sheet
    paper = np.zeros(gray.shape, np.uint8)
    cv2.fillConvexPoly(paper, hull, 255)
    paper = cv2.resize(paper, (width, height), interpolation=cv2.INTER_NEAREST)
    margin = max(3, round(width * 0.015))
    return cv2.erode(paper, np.ones((margin, margin), np.uint8))


def _components(mask: np.ndarray) -> tuple[list[Box], np.ndarray, float]:
    """Boxes of marks that could be part of a character, a mask of just them, and their typical area."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    height, width = mask.shape
    kept: list[tuple[Box, int, int]] = []
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        if area < 6:
            continue
        if x == 0 or y == 0 or x + w >= width or y + h >= height:
            continue  # touches the edge of the photo: paper edge, desk, thumb
        if w > width * 0.2 or h > height * 0.2:
            continue  # a line, a shadow or a page edge, not a character
        kept.append(((x, y, x + w, y + h), area, index))
    if not kept:
        return [], np.zeros_like(mask), 0.0
    typical = float(median(area for _, area, _ in kept))
    typical_height = float(median(box[3] - box[1] for box, _, _ in kept))
    boxes, indices = [], []
    for (x0, y0, x1, y1), area, index in kept:
        w, h = x1 - x0, y1 - y0
        if area < max(6, typical * 0.01):
            continue  # dust
        if (w > 2.5 * typical_height and h * 6 < w) or (h > 2.5 * typical_height and w * 6 < h):
            continue  # a streak far longer than any character: a crease, edge or line
        boxes.append((x0, y0, x1, y1))
        indices.append(index)
    clean = np.isin(labels, indices).astype(np.uint8) * 255
    return boxes, clean, typical


def _bands(mask: np.ndarray) -> list[Band]:
    """Horizontal bands of writing, from the smoothed row profile of the ink."""
    profile = (mask > 0).sum(axis=1).astype(np.float32)
    window = max(3, mask.shape[0] // 200)
    smooth = np.convolve(profile, np.ones(window) / window, mode="same")
    if smooth.max() <= 0:
        return []
    inked = smooth > smooth.max() * 0.03
    runs: list[list[int]] = []
    start: int | None = None
    for y, on in enumerate(inked):
        if on and start is None:
            start = y
        elif not on and start is not None:
            runs.append([start, y])
            start = None
    if start is not None:
        runs.append([start, len(inked)])
    typical = median(end - begin for begin, end in runs)
    merged = [runs[0]]
    for begin, end in runs[1:]:
        if begin - merged[-1][1] < typical * 0.3:
            merged[-1][1] = end
        else:
            merged.append([begin, end])
    typical = median(end - begin for begin, end in merged)
    return [Band(begin, end) for begin, end in merged if end - begin >= typical * 0.25]


def _nearest_band(box: Box, bands: list[Band]) -> int:
    _, y0, _, y1 = box
    overlaps = [max(0, min(y1, band.bottom) - max(y0, band.top)) for band in bands]
    if max(overlaps) > 0:
        return int(np.argmax(overlaps))
    distances = [max(band.top - y1, y0 - band.bottom) for band in bands]
    return int(np.argmin(distances))


def _union(a: Box, b: Box) -> Box:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _groups(members: list[Box], band: Band, expected: int) -> list[Box]:
    """Join marks into characters, left to right, until the row holds ``expected`` of them."""
    tolerance = band.height * 0.08
    groups: list[Box] = []
    for box in sorted(members):
        if groups and box[0] <= groups[-1][2] + tolerance:
            groups[-1] = _union(groups[-1], box)  # dots, second strokes, crossing parts
        else:
            groups.append(box)
    while len(groups) > expected:
        gaps = [groups[i + 1][0] - groups[i][2] for i in range(len(groups) - 1)]
        closest = int(np.argmin(gaps))
        groups[closest : closest + 2] = [_union(groups[closest], groups[closest + 1])]
    return groups


def capture_freehand(photos: list[Path], characters: str, columns: int) -> Capture:
    """Read rows of characters from photographs of plain or ruled paper.

    The writer copies the character set row by row with ``columns`` characters per row,
    leaving gaps between characters and between rows. Photos are read top to bottom in
    the order given.
    """
    rows = [characters[start : start + columns] for start in range(0, len(characters), columns)]
    sheets: list[np.ndarray] = []
    found: list[tuple[int, Band]] = []  # (photo index, band)
    marks: list[Box] = []
    offset = 0
    typical_areas: list[float] = []
    for photo_index, photo in enumerate(photos):
        rgb = load_image(photo)
        paper = _paper_mask(rgb)
        mask = cv2.bitwise_and(ink_mask(rgb), paper)
        angle = _skew_angle(mask)  # ruled lines, when present, sharpen the estimate
        if abs(angle) >= 0.25:
            rgb = _rotate(rgb, angle, (255, 255, 255))
            paper = _rotate(paper, angle, 0)
            mask = cv2.bitwise_and(ink_mask(rgb), paper)
        rgb, mask = _remove_lines(rgb, mask)
        boxes, clean, typical = _components(mask)
        typical_areas.append(typical)
        found.extend(
            (photo_index, Band(band.top + offset, band.bottom + offset)) for band in _bands(clean)
        )
        marks.extend((x0, y0 + offset, x1, y1 + offset) for x0, y0, x1, y1 in boxes)
        sheets.append(rgb)
        offset += rgb.shape[0]
    width = max(sheet.shape[1] for sheet in sheets)
    sheet = np.vstack(
        [np.pad(s, ((0, 0), (0, width - s.shape[1]), (0, 0)), constant_values=255) for s in sheets]
    )
    # A row of floating marks (quotes, ^, =) can split into two bands; like characters
    # within a row, bands are joined closest-first until the expected count is reached.
    while len(found) > len(rows):
        gaps = [
            (b.top - a.bottom, index)
            for index, ((pa, a), (pb, b)) in enumerate(zip(found, found[1:], strict=False))
            if pa == pb
        ]
        if not gaps:
            break
        _, index = min(gaps)
        page, upper = found[index]
        found[index : index + 2] = [(page, Band(upper.top, found[index + 1][1].bottom))]
    bands = [band for _, band in found]
    if len(bands) != len(rows):
        raise LayoutError(
            f"Found {len(bands)} rows of writing but expected {len(rows)} rows of {columns}"
            " characters. Copy the rows exactly as shown, leaving space between rows",
            sheet,
            marks,
        )
    members: list[list[Box]] = [[] for _ in bands]
    for box in marks:
        members[_nearest_band(box, bands)].append(box)
    boxes: dict[str, Box] = {}
    for index, (band, row) in enumerate(zip(bands, rows, strict=True)):
        groups = _groups(members[index], band, len(row))
        if len(groups) < len(row):
            raise LayoutError(
                f"Row {index + 1} holds {len(groups)} characters but should hold {len(row)}"
                f" ({row}). Leave a clear gap between characters",
                sheet,
                marks,
            )
        pad = max(2, round(band.height * 0.04))
        for character, (x0, y0, x1, y1) in zip(row, groups, strict=True):
            boxes[character] = (
                max(0, x0 - pad),
                max(0, y0 - pad),
                min(width, x1 + pad),
                min(sheet.shape[0], y1 + pad),
            )
    # A period or a backtick is a small fraction of a letter, so the floor scales with the writing.
    min_ink = max(16, round(min(MIN_INK_PIXELS, max(typical_areas) * 0.03)))
    cells = trace_cells(sheet, boxes, min_ink=min_ink)
    faint = [character for character, cell in cells.items() if cell is None]
    if faint:
        raise LayoutError(
            f"These characters are too faint or small to trace: {' '.join(faint)}",
            sheet,
            list(boxes.values()),
        )
    written = {character: cell for character, cell in cells.items() if cell is not None}
    bottoms = {character: cell[1][3] for character, cell in written.items()}
    baselines: dict[str, float] = {}
    for row in rows:
        sitters = [
            bottoms[c] for c in row if (c.isalnum() and c not in BELOW_BASELINE) or c in ROW_SITTERS
        ]
        baseline = median(sitters) if sitters else median(bottoms[c] for c in row)
        for character in row:
            baselines[character] = baseline
    glyphs, masks = derive_glyphs(written, boxes, baselines, characters, remove_shift=False)
    manifest = Manifest(width, tuple(glyphs), auto_aliases(masks))
    return Capture(manifest, masks, sheet)
