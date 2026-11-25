"""Поиск шрифтов с поддержкой кириллицы на Windows (с запасными вариантами)."""
from __future__ import annotations

import glob
import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# ключ -> (подпись в интерфейсе, файлы-кандидаты)
FONTS: dict[str, tuple[str, list[str]]] = {
    "auto": ("Авто (Bahnschrift / Segoe UI)", ["bahnschrift.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]),
    "bahnschrift": ("Bahnschrift", ["bahnschrift.ttf"]),
    "segoeui": ("Segoe UI Bold", ["segoeuib.ttf"]),
    "arial": ("Arial Bold", ["arialbd.ttf", "Arial_Bold.ttf", "LiberationSans-Bold.ttf"]),
    "impact": ("Impact", ["impact.ttf"]),
    "georgia": ("Georgia Bold", ["georgiab.ttf"]),
    "consolas": ("Consolas Bold", ["consolab.ttf"]),
    "custom": ("Свой файл шрифта…", []),
}
FONT_KEYS = tuple(FONTS)

_AUTO_FALLBACKS = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf"]


def _font_dirs() -> list[str]:
    dirs: list[str] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        dirs.append(os.path.join(windir, "Fonts"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]
    return dirs


@lru_cache(maxsize=64)
def _locate(filename: str) -> str | None:
    for directory in _font_dirs():
        direct = os.path.join(directory, filename)
        if os.path.isfile(direct):
            return direct
        if os.path.isdir(directory):
            hits = glob.glob(os.path.join(directory, "**", filename), recursive=True)
            if hits:
                return hits[0]
    return None


def find_font_path(key: str, custom_path: str = "") -> str | None:
    if key == "custom":
        return custom_path if custom_path and Path(custom_path).is_file() else None
    candidates = list(FONTS.get(key, FONTS["auto"])[1])
    if key in ("auto", "arial", "bahnschrift", "segoeui", "impact", "georgia", "consolas"):
        candidates += _AUTO_FALLBACKS
    for name in candidates:
        found = _locate(name)
        if found:
            return found
    return None


@lru_cache(maxsize=128)
def _load(path: str | None, size: int):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def load_font(key: str, custom_path: str, size: int):
    return _load(find_font_path(key, custom_path), max(8, int(size)))
