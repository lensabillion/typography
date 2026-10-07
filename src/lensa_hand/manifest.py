"""Input manifest loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SIDEBEARING = 55
DEFAULT_WORD_SPACE = 320
MAX_SIDEBEARING = 500


@dataclass(frozen=True)
class GlyphSpec:
    character: str
    box: tuple[int, int, int, int]
    height: int
    bottom: int
    left: int | None = None
    right: int | None = None


@dataclass(frozen=True)
class Manifest:
    coordinate_width: int
    glyphs: tuple[GlyphSpec, ...]
    aliases: dict[str, str]
    sidebearing: int = DEFAULT_SIDEBEARING
    word_space: int = DEFAULT_WORD_SPACE

    def left_bearing(self, spec: GlyphSpec) -> int:
        return self.sidebearing if spec.left is None else spec.left

    def right_bearing(self, spec: GlyphSpec) -> int:
        return self.sidebearing if spec.right is None else spec.right


def _bearing(item: dict, key: str, label: str) -> int | None:
    value = item.get(key)
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= MAX_SIDEBEARING:
        raise ValueError(f"{label}.{key} must be an integer in 0..{MAX_SIDEBEARING}")
    return value


def _metrics(data: dict) -> tuple[int, int]:
    metrics = data.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    unknown = set(metrics) - {"sidebearing", "word_space"}
    if unknown:
        raise ValueError(f"metrics has unknown keys: {', '.join(sorted(unknown))}")
    sidebearing = metrics.get("sidebearing", DEFAULT_SIDEBEARING)
    if type(sidebearing) is not int or not 0 <= sidebearing <= MAX_SIDEBEARING:
        raise ValueError(f"metrics.sidebearing must be an integer in 0..{MAX_SIDEBEARING}")
    word_space = metrics.get("word_space", DEFAULT_WORD_SPACE)
    if type(word_space) is not int or not 1 <= word_space <= 2000:
        raise ValueError("metrics.word_space must be an integer in 1..2000")
    return sidebearing, word_space


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")
    coordinate_width = data.get("coordinate_width")
    if type(coordinate_width) is not int or coordinate_width <= 0:
        raise ValueError("coordinate_width must be a positive integer")
    raw_glyphs = data.get("glyphs")
    if not isinstance(raw_glyphs, list) or not raw_glyphs:
        raise ValueError("glyphs must be a non-empty list")
    glyphs: list[GlyphSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_glyphs):
        label = f"glyphs[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object")
        character = item.get("character")
        if not isinstance(character, str) or len(character) != 1 or character in {" ", " "}:
            raise ValueError(f"{label}.character must be one non-space character")
        if character in seen:
            raise ValueError(f"Duplicate glyph: {character!r}")
        seen.add(character)
        box = item.get("box")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(type(value) is not int for value in box)
        ):
            raise ValueError(f"{label}.box must contain four integers")
        x1, y1, x2, y2 = box
        if min(x1, y1) < 0 or x2 <= x1 or y2 <= y1 or x2 > coordinate_width:
            raise ValueError(f"{label}.box is invalid: {box}")
        height = item.get("height")
        bottom = item.get("bottom")
        if type(height) is not int or height <= 0 or height > 2000:
            raise ValueError(f"{label}.height must be in 1..2000")
        if type(bottom) is not int or not -1000 <= bottom <= 1500:
            raise ValueError(f"{label}.bottom must be in -1000..1500")
        glyphs.append(
            GlyphSpec(
                character,
                (x1, y1, x2, y2),
                height,
                bottom,
                _bearing(item, "left", label),
                _bearing(item, "right", label),
            )
        )
    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError("aliases must be an object")
    for alias, source in aliases.items():
        if (
            not isinstance(alias, str)
            or len(alias) != 1
            or not isinstance(source, str)
            or source not in seen | {" "}
        ):
            raise ValueError(f"Invalid alias {alias!r}: target must be traced or space")
        if alias in seen or alias == " ":
            raise ValueError(f"Alias {alias!r} conflicts with a glyph or space")
    sidebearing, word_space = _metrics(data)
    return Manifest(coordinate_width, tuple(glyphs), aliases, sidebearing, word_space)
