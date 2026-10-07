"""Build a typeface from photographed handwriting: a printed template, plain paper or a crop map."""

from .bundle import install_skill, skill_text, write_package
from .install import install_font
from .pipeline import (
    build_from_paper,
    build_from_photos,
    build_from_template,
    build_project,
    validate_font,
)
from .template import DEFAULT_CHARACTERS, write_template

__all__ = [
    "DEFAULT_CHARACTERS",
    "build_from_paper",
    "build_from_photos",
    "build_from_template",
    "build_project",
    "install_font",
    "install_skill",
    "skill_text",
    "validate_font",
    "write_package",
    "write_template",
]
