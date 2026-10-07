"""Install a built font for the current user's desktop applications."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from fontTools.ttLib import TTFont

from .pipeline import validate_font

WINDOWS_FONT_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"


def font_directory(system: str, home: Path) -> Path:
    """Where the current user's fonts live on each operating system."""
    if system == "Darwin":
        return home / "Library" / "Fonts"
    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return local / "Microsoft" / "Windows" / "Fonts"
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return data / "fonts"


def install_font(ttf: Path, *, system: str | None = None, home: Path | None = None) -> Path:
    """Copy a validated TrueType font into the user's font folder and register it."""
    ttf = Path(ttf)
    if ttf.suffix.lower() != ".ttf":
        raise ValueError("Install the .ttf file; the .woff2 is for websites only")
    validate_font(ttf)
    system = system or platform.system()
    home = home or Path.home()
    directory = font_directory(system, home)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ttf.name
    shutil.copyfile(ttf, destination)
    if system == "Windows":
        _register_windows(destination)
    elif system == "Linux" and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", str(directory)], check=False, capture_output=True)
    return destination


def _register_windows(destination: Path) -> None:
    """Per-user fonts on Windows need a registry value, and running apps need a nudge."""
    try:
        import winreg  # noqa: PLC0415 - only exists on Windows
    except ImportError:
        return
    with TTFont(destination) as font:
        full_name = font["name"].getDebugName(4) or destination.stem
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_FONT_KEY) as key:
        winreg.SetValueEx(key, f"{full_name} (TrueType)", 0, winreg.REG_SZ, str(destination))
    try:
        import ctypes  # noqa: PLC0415

        ctypes.windll.gdi32.AddFontResourceW(str(destination))
        broadcast, font_change, abort_if_hung = 0xFFFF, 0x001D, 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            broadcast, font_change, 0, 0, abort_if_hung, 1000, None
        )
    except AttributeError, OSError:
        pass  # The registry value still makes the font appear after the next sign-in.
