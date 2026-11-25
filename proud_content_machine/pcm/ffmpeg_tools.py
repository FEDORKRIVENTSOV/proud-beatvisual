"""Поиск FFmpeg и общие параметры запуска подпроцессов."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import project_root


class FFmpegNotFoundError(RuntimeError):
    pass


_cached: str | None = None


def subprocess_kwargs() -> dict:
    """Скрывает консольное окно ffmpeg на Windows."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _works(exe: str) -> bool:
    try:
        result = subprocess.run([exe, "-version"], capture_output=True, timeout=15, **subprocess_kwargs())
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_ffmpeg() -> str:
    """Порядок: PCM_FFMPEG, imageio-ffmpeg (ставится install.bat), bin/ffmpeg(.exe), PATH."""
    global _cached
    if _cached and Path(_cached).is_file():
        return _cached
    candidates: list[str] = []
    env = os.environ.get("PCM_FFMPEG")
    if env:
        candidates.append(env)
    try:
        import imageio_ffmpeg

        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001 - любая проблема с пакетом не должна ломать поиск
        pass
    candidates.append(str(project_root() / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")))
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(found)
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and _works(candidate):
            _cached = candidate
            return candidate
    raise FFmpegNotFoundError(
        "FFmpeg не найден. Запустите install.bat (он ставит пакет imageio-ffmpeg) "
        "или положите ffmpeg.exe в папку bin рядом с программой."
    )
