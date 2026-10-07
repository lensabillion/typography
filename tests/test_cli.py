"""Check user-facing CLI behavior for common input errors and the happy path."""

from pathlib import Path

import pytest

from handfont.cli import main


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
    assert capsys.readouterr().out.startswith("handfont 0.")


def test_build_reports_every_deliverable(
    specimen: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image, manifest = specimen
    output = tmp_path / "out"
    args = ["build", "--photo", str(image), "--manifest", str(manifest), "--output", str(output)]
    assert main([*args, "--family", "Lensa Hand"]) == 0
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
    args = ["build", "--photo", str(image), "--manifest", str(manifest), "--output", str(output)]
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
                "--photo",
                str(tmp_path / "missing.jpg"),
                "--manifest",
                str(manifest),
                "--family",
                "Any",
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


def test_template_command_writes_pdf_and_pages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "sheet"
    assert (
        main(["template", "--output", str(output), "--characters", "abc", "--title", "Mini"]) == 0
    )
    assert (output / "template.pdf").is_file() and (output / "template-page-1.png").is_file()
    text = capsys.readouterr().out
    assert "handfont build --photo" in text and "No printer?" in text and "  1   a  b  c" in text
    assert main(["template", "--output", str(output), "--characters", "aab"]) == 1
    assert "repeats" in capsys.readouterr().err


def test_manifest_mode_accepts_one_photo_only(
    specimen: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image, manifest = specimen
    args = ["build", "--photo", str(image), "--photo", str(image), "--manifest", str(manifest)]
    assert main([*args, "--family", "Twice", "--output", str(tmp_path / "out")]) == 1
    assert "exactly one photo" in capsys.readouterr().err


def test_characters_do_not_apply_to_manifest_builds(
    specimen: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image, manifest = specimen
    args = ["build", "--photo", str(image), "--manifest", str(manifest), "--characters", "oi"]
    assert main([*args, "--family", "Mixed", "--output", str(tmp_path / "out")]) == 1
    assert "--characters applies to" in capsys.readouterr().err
