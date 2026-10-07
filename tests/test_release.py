"""Regression checks for the files shipped in ``fonts/``; they need no private photograph."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from handfont.manifest import load_manifest
from handfont.pipeline import validate_font

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
MANIFEST = ROOT / "config" / "alphabet.json"
TTF = FONTS / "LensaHand-Regular.ttf"
WOFF2 = FONTS / "LensaHand-Regular.woff2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("font", [TTF, WOFF2], ids=["ttf", "woff2"])
def test_shipped_font_validates_against_manifest(font: Path) -> None:
    manifest = load_manifest(MANIFEST)
    result = validate_font(font, MANIFEST)
    mapped = {32, 160} | {ord(alias) for alias in manifest.aliases}
    assert result["characters"] == len(manifest.glyphs) + len(mapped)
    assert result["glyphs"] == len(manifest.glyphs) + 2  # .notdef and space


def test_shipped_ttf_and_woff2_agree() -> None:
    with TTFont(TTF) as desktop, TTFont(WOFF2) as web:
        assert desktop.getBestCmap() == web.getBestCmap()
        assert desktop["hmtx"].metrics == web["hmtx"].metrics
        assert desktop["name"].getDebugName(1) == "Lensa Hand"


def test_shipped_build_matches_current_manifest() -> None:
    info = json.loads((FONTS / "build-info.json").read_text(encoding="utf-8"))
    assert info["manifest_sha256"] == sha256(MANIFEST), "manifest changed; rebuild fonts/"
    assert info["traced_glyphs"] == len(load_manifest(MANIFEST).glyphs)


def test_quality_record_matches_shipped_checksums() -> None:
    record = (ROOT / "docs" / "QUALITY.md").read_text(encoding="utf-8")
    assert re.findall(r"`([0-9a-f]{64})`", record) == [sha256(TTF), sha256(WOFF2)]


def test_shipped_web_assets_reference_shipped_files() -> None:
    css = (FONTS / "fonts.css").read_text(encoding="utf-8")
    assert f"url('./{WOFF2.name}')" in css
    tester = (FONTS / "preview.html").read_text(encoding="utf-8")
    assert WOFF2.name in tester and TTF.name in tester


def test_shipped_font_version_matches_manifest() -> None:
    version_name, revision = load_manifest(MANIFEST).revision()
    with TTFont(TTF) as font:
        assert font["name"].getDebugName(5) == version_name
        assert round(font["head"].fontRevision, 3) == revision
