"""Пути, имена файлов и проверки файловой системы (Windows-safe, кириллица, пробелы)."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

APP_DIR_NAME = "ProudContentMachine"
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    """Папка настроек и логов. Переопределяется переменной PCM_DATA_DIR (используется в тестах)."""
    override = os.environ.get("PCM_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = (Path(appdata) if appdata else Path.home() / "AppData" / "Roaming") / APP_DIR_NAME
    else:
        base = Path.home() / ".config" / APP_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_output_dir() -> Path:
    videos = Path.home() / "Videos"
    parent = videos if videos.is_dir() else Path.home()
    return parent / "Proud Content Machine"


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Превращает произвольное название в допустимое имя файла Windows. Кириллица и пробелы сохраняются."""
    cleaned = _INVALID_CHARS.sub("_", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .")
    if not cleaned:
        return "untitled"
    if cleaned.split(".")[0].upper() in _RESERVED_NAMES:
        cleaned = "_" + cleaned
    return cleaned


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Возвращает путь, которого ещё нет. Существующие файлы пользователя не перезаписываются."""
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def check_writable(directory: str | Path) -> str | None:
    """Создаёт папку при необходимости и проверяет запись. Возвращает текст ошибки или None."""
    try:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".pcm_write_test_", delete=True):
            pass
    except OSError as exc:
        return f"Папка недоступна для записи: {directory} ({exc})"
    return None


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    return f"{minutes}:{rest:06.3f}"


def parse_time(text: str) -> float:
    """Разбирает '1:23.5', '83.5', '1:02'. Бросает ValueError при неверном формате."""
    text = (text or "").strip().replace(",", ".")
    if not text:
        raise ValueError("пустое значение времени")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError("неверный формат времени")
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    if total < 0:
        raise ValueError("время не может быть отрицательным")
    return total
