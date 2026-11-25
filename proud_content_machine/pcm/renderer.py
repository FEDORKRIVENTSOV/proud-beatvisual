"""Рендер кадров шаблона и кодирование в MP4 через FFmpeg (кадры идут по pipe)."""
from __future__ import annotations

import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from .config import QUALITY
from .ffmpeg_tools import subprocess_kwargs
from .templates.base import VisualTemplate


class RenderError(RuntimeError):
    pass


class RenderCancelled(RuntimeError):
    pass


def build_ffmpeg_command(ffmpeg: str, width: int, height: int, fps: int, wav_path: str, out_path: str, quality: str) -> list[str]:
    crf, preset = QUALITY[quality]
    return [
        ffmpeg, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0",
        "-i", wav_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        out_path,
    ]


def render_video(
    template: VisualTemplate,
    ffmpeg: str,
    wav_path: str | Path,
    out_path: str | Path,
    quality: str,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Рендерит все кадры шаблона и кодирует их вместе со звуком. out_path лучше передавать ASCII-путём."""
    cmd = build_ffmpeg_command(ffmpeg, template.w, template.h, template.fps, str(wav_path), str(out_path), quality)
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **subprocess_kwargs())
    except OSError as exc:
        raise RenderError(f"Не удалось запустить FFmpeg: {exc}") from exc
    tail: deque[str] = deque(maxlen=20)

    def drain() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            tail.append(line.decode("utf-8", errors="replace").rstrip())

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    total = template.n_frames
    try:
        for i in range(total):
            if cancel is not None and cancel.is_set():
                raise RenderCancelled("Экспорт отменён")
            try:
                proc.stdin.write(template.render(i).tobytes())  # type: ignore[union-attr]
            except (BrokenPipeError, OSError) as exc:
                proc.wait()
                reader.join(timeout=2)
                raise RenderError("FFmpeg завершился с ошибкой: " + " | ".join(tail)) from exc
            if progress is not None:
                progress(i + 1, total)
        proc.stdin.close()  # type: ignore[union-attr]
        code = proc.wait()
        reader.join(timeout=5)
        if code != 0:
            raise RenderError("FFmpeg завершился с ошибкой: " + " | ".join(tail))
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        for stream in (proc.stdin, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        reader.join(timeout=2)
