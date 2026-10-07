"""The printable writing template, and the fixed geometry the camera side relies on."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont

from .manifest import Box

DPI = 300
_PX_PER_MM = DPI / 25.4

# Every printable ASCII character except space, in writing order.
DEFAULT_CHARACTERS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    ".,;:!?'\"()[]{}<>-_/\\|@#$%&*+=^~`"
)
LABEL_HINTS = {
    "l": "l  (lowercase L)",
    "I": "I  (capital i)",
    "O": "O  (capital o)",
    "0": "0  (zero)",
    "1": "1  (one)",
}
MARKER_DICTIONARY = cv2.aruco.DICT_4X4_50
MARKERS_PER_PAGE = 4
MAX_PAGES = 50 // MARKERS_PER_PAGE


def mm(value: float) -> int:
    """Millimetres to template pixels."""
    return round(value * _PX_PER_MM)


@dataclass(frozen=True)
class Layout:
    """Template geometry in millimetres on an A4 page; the content also fits US Letter.

    Printing at a different scale is fine: the camera side recovers the geometry from
    the corner markers, not from the paper size.
    """

    page_width: float = 210
    page_height: float = 297
    margin_x: float = 15
    grid_top: float = 26
    columns: int = 9
    rows: int = 11
    cell_width: float = 20
    cell_height: float = 20.7
    header: float = 3  # label strip at the top of each cell
    baseline: float = 10.5  # below the top of the writing area: 9 mm above it inside the crop
    x_height: float = 4.0  # above the baseline; 5.7 mm remain below it for descenders
    inset: float = 1.5  # crop margin inside the writing area, clear of borders and ticks
    tick: float = 1.0
    marker: float = 12
    marker_inset: float = 10

    @property
    def cells_per_page(self) -> int:
        return self.columns * self.rows

    @property
    def size(self) -> tuple[int, int]:
        return mm(self.page_width), mm(self.page_height)

    def pages(self, characters: str) -> list[str]:
        size = self.cells_per_page
        return [characters[start : start + size] for start in range(0, len(characters), size)]

    def cell(self, index: int) -> Box:
        column, row = index % self.columns, index // self.columns
        x0 = self.margin_x + column * self.cell_width
        y0 = self.grid_top + row * self.cell_height
        return mm(x0), mm(y0), mm(x0 + self.cell_width), mm(y0 + self.cell_height)

    def writing_area(self, index: int) -> Box:
        x0, y0, x1, y1 = self.cell(index)
        return x0, y0 + mm(self.header), x1, y1

    def crop_box(self, index: int) -> Box:
        x0, y0, x1, y1 = self.writing_area(index)
        inset = mm(self.inset)
        return x0 + inset, y0 + inset, x1 - inset, y1 - inset

    def baseline_y(self, index: int) -> int:
        return self.writing_area(index)[1] + mm(self.baseline)

    def x_height_y(self, index: int) -> int:
        return self.baseline_y(index) - mm(self.x_height)

    def marker_boxes(self) -> list[Box]:
        """Top-left, top-right, bottom-left and bottom-right marker squares."""
        near, far_x = self.marker_inset, self.page_width - self.marker_inset - self.marker
        far_y = min(self.page_height, 279) - self.marker_inset - self.marker  # fits US Letter
        size = mm(self.marker)
        return [
            (mm(x), mm(y), mm(x) + size, mm(y) + size)
            for x, y in ((near, near), (far_x, near), (near, far_y), (far_x, far_y))
        ]

    def marker_ids(self, page: int) -> list[int]:
        return [page * MARKERS_PER_PAGE + corner for corner in range(MARKERS_PER_PAGE)]


def check_characters(characters: str) -> str:
    if not characters:
        raise ValueError("The character set is empty")
    if any(character.isspace() for character in characters):
        raise ValueError("The character set must not contain spaces; space is always included")
    seen: set[str] = set()
    for character in characters:
        if character in seen:
            raise ValueError(f"The character set repeats {character!r}")
        seen.add(character)
    limit = MAX_PAGES * Layout().cells_per_page
    if len(characters) > limit:
        raise ValueError(
            f"The character set holds {len(characters)} characters; at most {limit} fit"
        )
    return characters


def render_page(
    layout: Layout, characters: str, page: int, page_count: int, title: str
) -> Image.Image:
    """Draw one template page: corner markers, instructions and a labelled cell per character."""
    image = Image.new("RGB", layout.size, "white")
    draw = ImageDraw.Draw(image)
    dictionary = cv2.aruco.getPredefinedDictionary(MARKER_DICTIONARY)
    for marker_id, (x0, y0, x1, _) in zip(
        layout.marker_ids(page), layout.marker_boxes(), strict=True
    ):
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, x1 - x0)
        image.paste(Image.fromarray(marker).convert("RGB"), (x0, y0))
    heading = ImageFont.load_default(size=mm(3.2))
    small = ImageFont.load_default(size=mm(2.2))
    label = ImageFont.load_default(size=mm(2.2))
    hint = ImageFont.load_default(size=mm(1.8))
    left = mm(layout.marker_inset + layout.marker + 4)
    draw.text(
        (left, mm(9.5)), f"{title}  -  page {page + 1} of {page_count}", font=heading, fill="#222"
    )
    draw.text(
        (left, mm(14.5)),
        "Write one character per box with a black pen. Rest letters on the long tick;"
        " small letters reach the short tick.",
        font=small,
        fill="#555",
    )
    draw.text(
        (left, mm(18.5)),
        "Photograph the whole sheet flat, in even light, with all four corner squares in view.",
        font=small,
        fill="#555",
    )
    tick = mm(layout.tick)
    for index, character in enumerate(characters):
        x0, y0, x1, y1 = layout.cell(index)
        draw.rectangle((x0, y0, x1, y1), outline="#8c8c8c", width=mm(0.3))
        wx0, wy0, wx1, _ = layout.writing_area(index)
        draw.line((wx0, wy0, wx1, wy0), fill="#c8c8c8", width=mm(0.2))
        text = LABEL_HINTS.get(character, character)
        draw.text(
            (x0 + mm(1.2), y0 + mm(0.4)), text, font=hint if len(text) > 1 else label, fill="#333"
        )
        base, x_line = layout.baseline_y(index), layout.x_height_y(index)
        for edge, direction in ((wx0, 1), (wx1, -1)):
            draw.line((edge, base, edge + direction * tick, base), fill="#222", width=mm(0.4))
            draw.line(
                (edge, x_line, edge + direction * tick * 0.6, x_line), fill="#222", width=mm(0.3)
            )
    _, _, _, bottom = layout.cell(layout.cells_per_page - 1)
    draw.text((left, bottom + mm(2)), "handfont template", font=small, fill="#777")
    return image


def write_template(
    output: Path, characters: str = DEFAULT_CHARACTERS, title: str = "handfont template"
) -> list[Path]:
    """Write ``template.pdf`` plus one PNG per page; return the PDF first, then the pages."""
    check_characters(characters)
    layout = Layout()
    pages = layout.pages(characters)
    images = [
        render_page(layout, page, index, len(pages), title) for index, page in enumerate(pages)
    ]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    pdf = output / "template.pdf"
    images[0].save(pdf, save_all=True, append_images=images[1:], resolution=float(DPI))
    paths = [pdf]
    for number, image in enumerate(images, 1):
        path = output / f"template-page-{number}.png"
        image.save(path, dpi=(DPI, DPI))
        paths.append(path)
    return paths
