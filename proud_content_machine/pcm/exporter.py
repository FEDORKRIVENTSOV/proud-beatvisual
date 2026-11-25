"""Оркестрация экспорта: фрагмент аудио -> анализ -> по видео на каждый шаблон -> итоговые файлы."""
from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .audio import AudioData, analyze_segment, fade_samples, write_wav
from .config import JobConfig, validate_job
from .ffmpeg_tools import find_ffmpeg
from .paths import sanitize_filename, unique_path
from .renderer import RenderCancelled, RenderError, render_video
from .templates import get_template

log = logging.getLogger(__name__)


class ValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


class ExportCancelled(RuntimeError):
    def __init__(self, completed: list[Path]) -> None:
        super().__init__("Экспорт отменён")
        self.completed = completed


class ExportError(RuntimeError):
    def __init__(self, message: str, completed: list[Path]) -> None:
        super().__init__(message)
        self.completed = completed


@dataclass
class ExportProgress:
    job_index: int
    job_count: int
    template_id: str
    frame: int
    frame_count: int
    stage: str = "render"

    @property
    def fraction(self) -> float:
        if self.frame_count <= 0:
            return self.job_index / max(1, self.job_count)
        return (self.job_index + self.frame / self.frame_count) / max(1, self.job_count)


def export_job(
    job: JobConfig,
    audio: AudioData,
    progress: Callable[[ExportProgress], None] | None = None,
    cancel: threading.Event | None = None,
    ffmpeg: str | None = None,
) -> list[Path]:
    """Создаёт по одному MP4 на каждый выбранный шаблон. Существующие файлы не перезаписываются."""
    errors = validate_job(job, audio.duration)
    if errors:
        raise ValidationError(errors)
    ffmpeg = ffmpeg or find_ffmpeg()
    templates = list(dict.fromkeys(job.templates))
    out_dir = Path(job.output_dir)
    safe_title = sanitize_filename(job.visual.title)
    completed: list[Path] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="pcm_"))  # ASCII-путь для FFmpeg
    try:
        wav_path = tmp_dir / "segment.wav"
        segment = fade_samples(audio.segment_int16(job.start, job.end), audio.sample_rate, job.fade_in, job.fade_out)
        write_wav(wav_path, segment, audio.sample_rate)
        mono = audio.mono_float(job.start, job.end)
        if progress:
            progress(ExportProgress(0, len(templates), templates[0], 0, 0, "analyze"))
        features = analyze_segment(mono, audio.sample_rate, job.fps)
        for index, template_id in enumerate(templates):
            if cancel is not None and cancel.is_set():
                raise ExportCancelled(completed)
            template = get_template(template_id)(job.width, job.height, job.visual, features)
            tmp_out = tmp_dir / f"{template_id}.mp4"

            def on_frame(done: int, total: int, _i=index, _t=template_id) -> None:
                if progress:
                    progress(ExportProgress(_i, len(templates), _t, done, total))

            try:
                render_video(template, ffmpeg, wav_path, tmp_out, job.quality, on_frame, cancel)
            except RenderCancelled:
                raise ExportCancelled(completed) from None
            except RenderError as exc:
                raise ExportError(f"Шаблон «{template.name}»: {exc}", completed) from exc
            final = unique_path(out_dir, f"{safe_title}_{template_id}", ".mp4")
            try:
                shutil.move(str(tmp_out), str(final))
            except OSError as exc:
                raise ExportError(f"Не удалось сохранить файл {final}: {exc}", completed) from exc
            completed.append(final)
            log.info("Готово: %s", final)
        return completed
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
