"""Manifest validation: every rejected shape names the offending field."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from handfont.manifest import load_manifest, manifest_to_dict

BASE = {
    "coordinate_width": 100,
    "glyphs": [{"character": "a", "box": [0, 0, 10, 10], "height": 430, "bottom": 0}],
    "aliases": {},
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def patched(path: tuple, value: object) -> dict:
    data = copy.deepcopy(BASE)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("coordinate_width",), 0, "coordinate_width"),
        (("glyphs",), "abc", "non-empty list"),
        (("glyphs", 0), "a", "must be an object"),
        (("glyphs", 0, "character"), "ab", "one non-space character"),
        (("glyphs", 0, "box"), [0, 0, "x", 10], "four integers"),
        (("glyphs", 0, "box"), [0, 0, 200, 10], "box is invalid"),
        (("glyphs", 0, "height"), 0, "height"),
        (("glyphs", 0, "bottom"), -5000, "bottom"),
        (("glyphs", 0, "left"), 999, r"glyphs\[0\]\.left"),
        (("glyphs", 0, "right"), "wide", r"glyphs\[0\]\.right"),
        (("aliases",), [], "aliases must be an object"),
        (("aliases",), {"b": "z"}, "Invalid alias"),
        (("aliases",), {"a": "a"}, "conflicts"),
        (("metrics",), 5, "metrics must be an object"),
        (("metrics",), {"side_bearing": 1}, "unknown keys"),
        (("metrics",), {"sidebearing": -1}, "metrics.sidebearing"),
        (("metrics",), {"word_space": 0}, "metrics.word_space"),
        (("version",), "1", "version"),
        (("version",), 1.0, "version"),
        (("version",), "1.2345", "version"),
        (("version",), "01.0", "version"),
    ],
)
def test_invalid_manifests_name_the_field(
    tmp_path: Path, path: tuple, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_manifest(write(tmp_path, patched(path, value)))


def test_duplicate_glyphs_and_non_object_documents_are_rejected(tmp_path: Path) -> None:
    data = copy.deepcopy(BASE)
    data["glyphs"].append(copy.deepcopy(data["glyphs"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        load_manifest(write(tmp_path, data))
    with pytest.raises(ValueError, match="JSON object"):
        load_manifest(write(tmp_path, [1, 2]))


def test_metrics_default_and_override_per_glyph(tmp_path: Path) -> None:
    plain = load_manifest(write(tmp_path, BASE))
    assert (plain.sidebearing, plain.word_space) == (55, 320)
    assert (plain.left_bearing(plain.glyphs[0]), plain.right_bearing(plain.glyphs[0])) == (55, 55)
    data = patched(("metrics",), {"sidebearing": 40})
    data["glyphs"][0]["right"] = 12
    tuned = load_manifest(write(tmp_path, data))
    assert (tuned.sidebearing, tuned.word_space) == (40, 320)
    assert (tuned.left_bearing(tuned.glyphs[0]), tuned.right_bearing(tuned.glyphs[0])) == (40, 12)


def test_manifest_round_trips_through_json(tmp_path: Path) -> None:
    data = patched(("metrics",), {"sidebearing": 40, "word_space": 300})
    data["version"] = "0.7"
    data["glyphs"][0]["left"] = 5
    data["aliases"] = {"b": "a"}
    first = load_manifest(write(tmp_path, data))
    again = load_manifest(write(tmp_path, manifest_to_dict(first)))
    assert again == first
    assert first.revision() == ("Version 0.700", 0.7)
