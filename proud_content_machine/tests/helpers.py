import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from pcm.audio import SAMPLE_RATE, write_wav
from pcm.ffmpeg_tools import find_ffmpeg


def make_test_audio(path: Path, seconds: float = 6.0) -> Path:
    """Синтетический бит: кик 2 Гц, мелодия и шум. Стерео 16 бит."""
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    kick = 0.55 * np.sin(2 * np.pi * 60 * t) * np.exp(-8 * (t * 2 % 1.0))
    melody = 0.18 * np.sin(2 * np.pi * (440 + 110 * np.floor(t * 2 % 4)) * t)
    noise = 0.03 * np.random.default_rng(1).standard_normal(len(t))
    mono = np.clip(kick + melody + noise, -1, 1)
    stereo = np.stack([mono, mono * 0.9], axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(path, (stereo * 30000).astype(np.int16))
    return path


def media_info(path: Path) -> dict:
    """Разбор вывода `ffmpeg -i` (работает без ffprobe). Файл копируется во временный ASCII-путь."""
    tmp = Path(tempfile.mkdtemp()) / "probe.mp4"
    shutil.copyfile(path, tmp)
    try:
        err = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", str(tmp)], capture_output=True, text=True, errors="replace").stderr
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    video = re.search(r"Video: (\w+).*?, (\d+)x(\d+)", err)
    audio = re.search(r"Audio: (\w+)", err)
    return {
        "duration": int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else None,
        "vcodec": video[1] if video else None,
        "size": (int(video[2]), int(video[3])) if video else None,
        "acodec": audio[1] if audio else None,
    }
