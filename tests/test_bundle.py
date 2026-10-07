"""The npm package, the desktop installer and the agent skills."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from fontTools.ttLib import TTFont

from handfont.bundle import (
    install_skill,
    npm_version,
    package_name,
    release_tag,
    skill_text,
    write_package,
)
from handfont.font import build_font
from handfont.install import font_directory, install_font
from handfont.manifest import GlyphSpec, Manifest
from handfont.pipeline import build_project


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        ("Lensa Hand", "lensa-hand"),
        ("Ada's   Hand!", "ada-s-hand"),
        ("2nd Draft", "font-2nd-draft"),
        ("", "handwriting-font"),
    ],
)
def test_package_names_are_valid_npm_names(family: str, expected: str) -> None:
    assert package_name(family) == expected


def test_npm_version_from_design_version() -> None:
    assert npm_version("0.3") == "0.3.0"
    assert npm_version("2.15") == "2.15.0"


@pytest.fixture
def ring_font(tmp_path: Path) -> tuple[Path, Path, Manifest]:
    mask = np.zeros((80, 60), dtype=np.uint8)
    mask[3:77, 3:57] = 255
    mask[15:65, 15:45] = 0
    manifest = Manifest(60, (GlyphSpec("O", (0, 0, 60, 80), 650, 0),), {"“": "O"}, version="1.2")
    ttf, woff2 = build_font(manifest, {"O": mask}, tmp_path, "Ring Hand")
    return ttf, woff2, manifest


def test_package_is_complete_and_private_free(
    ring_font: tuple[Path, Path, Manifest], tmp_path: Path
) -> None:
    ttf, woff2, manifest = ring_font
    root = write_package(tmp_path, "Ring Hand", ttf, woff2, "O", manifest.aliases, manifest.version)
    names = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    assert names == [
        "AGENTS.md",
        "README.md",
        "SKILL.md",
        "fonts/RingHand-Regular.ttf",
        "fonts/RingHand-Regular.woff2",
        "index.css",
        "index.d.ts",
        "index.js",
        "package.json",
    ]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "ring-hand" and package["version"] == "1.2.0"
    assert package["exports"]["./index.css"] == "./index.css" and package["license"] == "UNLICENSED"
    assert (root / "fonts" / woff2.name).read_bytes() == woff2.read_bytes()
    css = (root / "index.css").read_text(encoding="utf-8")
    assert 'font-family: "Ring Hand";' in css and "./fonts/RingHand-Regular.woff2" in css
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: use-ring-hand-font\n")
    assert 'import "ring-hand/index.css";' in skill and "RingHand-Regular.woff2" in skill
    assert "$" not in skill  # every placeholder was filled
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "“ -> O" in readme and "npm install ring-hand" in readme
    assert "ring-hand" in (root / "AGENTS.md").read_text(encoding="utf-8")


def test_build_ships_the_package_inside_the_archive(
    specimen: tuple[Path, Path], tmp_path: Path
) -> None:
    image, manifest = specimen
    result = build_project(image, manifest, tmp_path / "out", "Lensa Hand")
    assert result.package == tmp_path / "out" / "package"
    with ZipFile(result.archive) as archive:
        names = archive.namelist()
    assert "package/package.json" in names and "package/fonts/LensaHand-Regular.woff2" in names
    assert "sheet.png" not in names and "manifest.json" not in names


@pytest.mark.parametrize(
    ("system", "relative"),
    [
        ("Darwin", "Library/Fonts"),
        ("Linux", ".local/share/fonts"),
        ("Windows", "AppData/Local/Microsoft/Windows/Fonts"),
    ],
)
def test_install_copies_into_the_user_font_folder(
    ring_font: tuple[Path, Path, Manifest],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    relative: str,
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("handfont.install.shutil.which", lambda _: None)
    ttf, _, _ = ring_font
    home = tmp_path / "home"
    destination = install_font(ttf, system=system, home=home)
    assert destination == home.joinpath(*relative.split("/")) / ttf.name
    assert destination.read_bytes() == ttf.read_bytes()
    assert font_directory(system, home) == destination.parent


def test_install_rejects_a_broken_font(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")
    with pytest.raises(ValueError, match="Cannot open font"):
        install_font(broken, system="Darwin", home=tmp_path / "home")
    assert not (tmp_path / "home").exists()


def test_skill_installs_where_claude_code_looks(tmp_path: Path) -> None:
    text = skill_text()
    assert text.startswith("---\nname: handfont\n")
    assert "handfont build --photo" in text and "layout-check.png" in text
    path = install_skill(tmp_path / "project")
    assert path == tmp_path / "project" / ".claude" / "skills" / "handfont" / "SKILL.md"
    assert path.read_text(encoding="utf-8") == text


def test_write_package_refuses_a_folder_it_did_not_write(
    ring_font: tuple[Path, Path, Manifest], tmp_path: Path
) -> None:
    ttf, woff2, manifest = ring_font
    foreign = tmp_path / "package"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(ValueError, match="not written by handfont"):
        write_package(tmp_path, "Ring Hand", ttf, woff2, "O", {}, "1.0")
    assert (foreign / "notes.txt").read_text(encoding="utf-8") == "mine"
    write_package(tmp_path / "fresh", "Ring Hand", ttf, woff2, "O", {}, "1.0")
    write_package(tmp_path / "fresh", "Ring Hand", ttf, woff2, "O", {}, "1.1")  # replaces its own
    package = json.loads(
        (tmp_path / "fresh" / "package" / "package.json").read_text(encoding="utf-8")
    )
    assert package["version"] == "1.1.0"


def test_skills_pin_the_release_tag() -> None:
    assert release_tag().startswith("v")
    assert f"typography@{release_tag()} handfont build" in skill_text()


def test_install_accepts_only_truetype(
    ring_font: tuple[Path, Path, Manifest], tmp_path: Path
) -> None:
    _, woff2, _ = ring_font
    with pytest.raises(ValueError, match=r"\.ttf"):
        install_font(woff2, system="Darwin", home=tmp_path / "home")


def test_windows_install_registers_the_font(
    ring_font: tuple[Path, Path, Manifest], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ttf, _, _ = ring_font
    written: dict[str, str] = {}

    class FakeKey:
        def __enter__(self) -> FakeKey:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        REG_SZ="REG_SZ",
        CreateKey=lambda hive, path: FakeKey(),
        SetValueEx=lambda key, name, reserved, kind, value: written.__setitem__(name, value),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    destination = install_font(ttf, system="Windows", home=tmp_path / "home")
    assert written == {"Ring Hand Regular (TrueType)": str(destination)}


def test_linux_install_refreshes_the_font_cache(
    ring_font: tuple[Path, Path, Manifest], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ttf, _, _ = ring_font
    calls: list[list[str]] = []
    monkeypatch.setattr("handfont.install.shutil.which", lambda _: "/usr/bin/fc-cache")
    monkeypatch.setattr("handfont.install.subprocess.run", lambda args, **kw: calls.append(args))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    destination = install_font(ttf, system="Linux", home=tmp_path / "home")
    assert calls == [["fc-cache", "-f", str(destination.parent)]]


def test_licensed_build_writes_the_notice_everywhere(
    specimen: tuple[Path, Path], tmp_path: Path
) -> None:
    image, manifest = specimen
    result = build_project(
        image,
        manifest,
        tmp_path / "out",
        "Lensa Hand",
        copyright="Copyright 2026 Ada",
        license="OFL-1.1",
    )
    assert result.license == tmp_path / "out" / "LICENSE.txt"
    notice = result.license.read_text(encoding="utf-8")
    assert notice.startswith('Copyright 2026 Ada, with Reserved Font Name "Lensa Hand".\n')
    assert "SIL OPEN FONT LICENSE Version 1.1" in notice
    with TTFont(result.ttf) as font:
        names = font["name"]
        assert names.getDebugName(0) == "Copyright 2026 Ada"
        assert "SIL Open Font License, Version 1.1" in names.getDebugName(13)
        assert names.getDebugName(14) == "https://openfontlicense.org"
    package = json.loads((result.package / "package.json").read_text(encoding="utf-8"))
    assert package["license"] == "OFL-1.1" and "LICENSE.txt" in package["files"]
    assert (result.package / "LICENSE.txt").read_text(encoding="utf-8") == notice
    assert "OFL-1.1" in (result.package / "README.md").read_text(encoding="utf-8")
    assert "License: OFL-1.1" in result.readme.read_text(encoding="utf-8")
    with ZipFile(result.archive) as archive:
        assert "LICENSE.txt" in archive.namelist() and "package/LICENSE.txt" in archive.namelist()
    with pytest.raises(ValueError, match="copyright holder"):
        build_project(image, manifest, tmp_path / "bad", "Lensa Hand", license="OFL-1.1")


def test_unlicensed_build_says_so(specimen: tuple[Path, Path], tmp_path: Path) -> None:
    image, manifest = specimen
    result = build_project(image, manifest, tmp_path / "out", "Lensa Hand")
    assert result.license is None
    assert not (result.package / "LICENSE.txt").exists()
    assert "none chosen yet" in result.readme.read_text(encoding="utf-8")
    with TTFont(result.ttf) as font:
        assert font["name"].getDebugName(13) is None
