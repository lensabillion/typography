"""Check user-facing CLI behavior for common input errors."""

from pathlib import Path

import pytest

from lensa_hand.cli import main


def test_help_lists_supported_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    text = capsys.readouterr().out
    assert "build" in text and "validate" in text


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
