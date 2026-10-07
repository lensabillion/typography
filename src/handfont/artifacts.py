"""Create reviewable specimens and a deterministic distribution archive."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from html import escape
from pathlib import Path
from statistics import median
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Box = tuple[int, int, int, int]


def _label_font(size: int):
    return ImageFont.load_default(size=size)


def _rows(characters: str) -> list[str]:
    """Group a character set into lowercase, uppercase, digit and other rows."""
    groups = [
        "".join(c for c in characters if c.islower()),
        "".join(c for c in characters if c.isupper()),
        "".join(c for c in characters if c.isdigit()),
        "".join(c for c in characters if not c.isalnum()),
    ]
    return [group for group in groups if group]


def write_tracing_sheet(glyphs: dict[str, np.ndarray], output: Path) -> Path:
    sheet = Image.new("RGB", (1000, ((len(glyphs) + 9) // 10) * 140), "#faf7ef")
    draw = ImageDraw.Draw(sheet)
    for index, (character, mask) in enumerate(glyphs.items()):
        x, y = (index % 10) * 100, (index // 10) * 140
        draw.text((x + 8, y + 5), character, fill="#292721", font=_label_font(18))
        factor = min(82 / mask.shape[1], 95 / mask.shape[0], 2)
        size = (max(1, round(mask.shape[1] * factor)), max(1, round(mask.shape[0] * factor)))
        picture = Image.fromarray(255 - mask).resize(size).convert("RGB")
        sheet.paste(picture, (x + 8, y + 30))
    path = output / "tracing-check.png"
    sheet.save(path)
    return path


def write_layout_check(sheet: np.ndarray, labels: list[tuple[str, Box]], output: Path) -> Path:
    """Draw every detected box with its label on the straightened sheet for review."""
    image = Image.fromarray(sheet).convert("RGB")
    draw = ImageDraw.Draw(image)
    typical = median(y1 - y0 for _, (_, y0, _, y1) in labels) if labels else 40
    size = max(12, round(typical * 0.45))
    font = _label_font(size)
    stroke = max(1, image.width // 900)
    for text, (x0, y0, x1, y1) in labels:
        draw.rectangle((x0, y0, x1, y1), outline="#d23b2a", width=stroke)
        draw.text((x0, max(0, y0 - 2)), text, fill="#d23b2a", font=font, anchor="ls")
    if image.width > 1800:
        factor = 1800 / image.width
        image = image.resize((1800, round(image.height * factor)))
    path = output / "layout-check.png"
    image.save(path)
    return path


def write_preview(ttf: Path, output: Path, family: str, characters: str) -> Path:
    covered = set(characters)
    preview = Image.new("RGB", (1600, 1100), "#fbf7ee")
    draw = ImageDraw.Draw(preview)
    label = _label_font(22)
    draw.text((85, 60), f"{family.upper()}  /  HANDWRITING FONT DRAFT", font=label, fill="#766a58")
    samples = [
        ("A little bit of my handwriting.", 140, 60),
        ("The quick brown fox jumps", 270, 55),
        ("over the lazy dog.", 355, 55),
        ("abcdefghijklmnopqrstuvwxyz", 510, 43),
        ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 610, 42),
        ("0123456789", 740, 65),
        ("Hello, world! How are you?", 865, 55),
    ]
    for sample, y, size in samples:
        text = "".join(c for c in sample if c == " " or c in covered)
        if text.strip():
            font = ImageFont.truetype(str(ttf), size)
            draw.text((85, y), text, font=font, fill="#33302c")
    draw.text(
        (85, 1030),
        "Original traced letterforms  /  Spacing and joining ready for refinement",
        font=label,
        fill="#766a58",
    )
    path = output / f"{ttf.stem.removesuffix('-Regular')}-preview.png"
    preview.save(path)
    return path


def write_tester(
    ttf: Path,
    woff2: Path,
    output: Path,
    family: str,
    characters: str,
    skipped: Sequence[str] = (),
) -> Path:
    safe_family = escape(family)
    rows = "<br>".join(escape(row) for row in _rows(characters))
    missing = (
        f"<p><small>Not written on the sheet: {escape(' '.join(skipped))}</small></p>"
        if skipped
        else ""
    )
    html = f'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_family} — font tester</title>
<style>
@font-face {{ font-family: Hand; src: url('{woff2.name}') format('woff2'); }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f8f4eb; color: #302e29; font: 16px system-ui; padding: 6vw; max-width: 1200px; }}
h1 {{ font-size: 20px; font-weight: 500; }}
p {{ color: #70675c; line-height: 1.6; }}
textarea {{ display: block; width: 100%; min-height: 360px; border: 1px solid #d8cfbe; border-radius: 8px; padding: 32px; background: #fffcf5; color: #302e29; font: 48px/1.6 Hand; resize: vertical; margin: 26px 0; }}
label {{ display: flex; gap: 18px; align-items: center; }}
a {{ color: inherit; }}
section {{ font: 40px/1.8 Hand; overflow-wrap: anywhere; margin-top: 45px; }}
small {{ font: 14px system-ui; color: #70675c; }}
</style>
<h1>{safe_family.upper()} · DRAFT</h1>
<p>Type below to try the traced handwriting.</p>
<label>Text size <input id="size" type="range" min="24" max="96" value="48"><output id="value">48 px</output></label>
<textarea id="text" spellcheck="false" aria-label="Try your handwriting font">A little bit of my handwriting.
The quick brown fox jumps over the lazy dog.</textarea>
<a href="{ttf.name}" download>Download the font (.ttf)</a>
<section>{rows}</section>
{missing}<p><small>One shape per character and no cursive joins. Characters outside the rows above come from your fallback font.</small></p>
<script>document.querySelector('#size').oninput=e=>{{document.querySelector('#text').style.fontSize=e.target.value+'px';document.querySelector('#value').textContent=e.target.value+' px'}}</script>
</html>
'''
    path = output / "preview.html"
    path.write_text(html, encoding="utf-8")
    return path


def write_css(woff2: Path, output: Path, family: str) -> Path:
    path = output / "fonts.css"
    family_css = family.replace("\\", "\\\\").replace("'", "\\'")
    path.write_text(
        "@font-face {\n"
        f"  font-family: '{family_css}';\n"
        f"  src: url('./{woff2.name}') format('woff2');\n"
        "  font-style: normal;\n"
        "  font-weight: 400;\n"
        "  font-display: swap;\n"
        "}\n",
        encoding="utf-8",
    )
    return path


def write_readme(
    output: Path,
    family: str,
    ttf: Path,
    woff2: Path,
    characters: str,
    aliases: dict[str, str],
    skipped: Sequence[str] = (),
) -> Path:
    missing = f"Not written on the sheet: {' '.join(skipped)}\n" if skipped else ""
    mapped = ", ".join(f"{alias} -> {source}" for alias, source in aliases.items() if source != " ")
    mapped = f"Also mapped onto written characters: {mapped}\n" if mapped else ""
    path = output / "README.txt"
    path.write_text(
        f"{family} — handwriting font\n\n"
        f"Install {ttf.name} in Font Book or another font manager.\n"
        "Open preview.html in a browser to test the font.\n\n"
        "The font traces a photographed handwriting sheet. The photographs are not included.\n\n"
        f"Characters: {characters}\n"
        f"{missing}{mapped}"
        "Limitations: one shape per character; no cursive joins or kerning.\n"
        "Keep a fallback font for anything else.\n\n"
        f"Files: {ttf.name} for desktop installation; {woff2.name} and fonts.css for web use; "
        "PNG specimens; HTML tester.\n",
        encoding="utf-8",
    )
    return path


def write_build_info(
    sources: Sequence[Path],
    manifest: Path,
    output: Path,
    family: str,
    glyph_count: int,
    mode: str,
    skipped: Sequence[str] = (),
    clipped: Sequence[str] = (),
) -> Path:
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    photos = []
    for source in sources:
        with Image.open(source) as image:
            dimensions = [image.width, image.height]
        photos.append({"name": source.name, "sha256": digest(source), "dimensions": dimensions})
    info = {
        "schema_version": 2,
        "family": family,
        "mode": mode,
        "sources": photos,
        "manifest_sha256": digest(manifest),
        "traced_glyphs": glyph_count,
        "skipped": list(skipped),
        "clipped": list(clipped),
    }
    path = output / "build-info.json"
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_archive(files: list[Path], output: Path, stem: str) -> Path:
    archive = output / f"{stem}-Draft.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(files, key=lambda item: item.name):
            info = ZipInfo(path.name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    return archive
