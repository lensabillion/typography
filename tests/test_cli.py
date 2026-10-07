"""Check user-facing CLI behavior for common input errors and the happy path."""

from pathlib import Path

import pytest

from lensa_hand.cli import main


def test_help_lists_supported_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    text = capsys.readouterr().out
    assert "build" in text and "validate" in text


def test_version_flag_reports_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.startswith("lensa-hand 0.")


def test_build_reports_every_deliverable(
    specimen: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image, manifest = specimen
    output = tmp_path / "out"
    args = ["build", "--source", str(image), "--manifest", str(manifest), "--output", str(output)]
    assert main(args) == 0
    text = capsys.readouterr().out
    assert "Built 2 traced glyphs" in text
    assert all(label in text for label in ("Web font:", "Preview:", "Archive:"))
    assert (
        main(["validate", str(output / "LensaHand-Regular.ttf"), "--manifest", str(manifest)]) == 0
    )
    assert "Valid font: 5 characters, 4 glyphs" in capsys.readouterr().out


def test_blank_family_fails_before_tracing(
    specimen: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image, manifest = specimen
    output = tmp_path / "out"
    args = ["build", "--source", str(image), "--manifest", str(manifest), "--output", str(output)]
    assert main([*args, "--family", "   "]) == 1
    assert "blank" in capsys.readouterr().err
    assert not output.exists()


def test_invalid_manifest_fails_without_creating_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "invalid.json"
    manifest.write_text("{", encoding="utf-8")
    output = tmp_path / "output"
    assert (
        main(
            [
                "build",
                "--source",
                str(tmp_path / "missing.jpg"),
                "--manifest",
                str(manifest),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert "Cannot read manifest" in capsys.readouterr().err
    assert not output.exists()


def test_invalid_font_returns_actionable_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    font = tmp_path / "broken.ttf"
    font.write_bytes(b"not a font")
    assert main(["validate", str(font)]) == 1
    assert "Cannot open font" in capsys.readouterr().err
