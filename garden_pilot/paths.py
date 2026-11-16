"""Filesystem locations that work both from source and from a frozen exe."""

from __future__ import annotations

import sys
from pathlib import Path


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


APP_DIR = _app_dir()
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
ASSETS_DIR = RESOURCE_DIR / "assets"
TEMPLATE_DIR = ASSETS_DIR / "templates"
ICON_PATH = ASSETS_DIR / "icon.png"
LOG_DIR = APP_DIR / "logs"
