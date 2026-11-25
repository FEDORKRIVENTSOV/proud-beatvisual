"""Состояние редактора без GUI: аудио, выбор фрагмента, предпросмотр. Легко тестируется."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image

from .audio import AudioData, AudioFeatures, analyze_segment, best_segment, compute_peaks, decode_audio, fade_samples, write_wav
from .config import MAX_SEGMENT_SEC, MIN_SEGMENT_SEC, RESOLUTIONS, JobConfig, VisualConfig
from .settings import AppSettings
from .templates import TEMPLATES, VisualTemplate

PREVIEW_FPS = 20
PEAK_COLUMNS = 1600


class Session:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.audio: AudioData | None = None
        self.peaks = None
        self.start = 0.0
        self.end = 0.0
        self.templates: list[str] = ["neon_wave"]
        self.visual = VisualConfig.from_dict(settings.visual)
        self._features_key = None
        self._features: AudioFeatures | None = None
        self._tpl_cache: dict = {}
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="pcm_preview_"))
        self._preview_counter = 0

    # ---- аудио ------------------------------------------------------------
    def load_audio(self, path: str | Path) -> AudioData:
        audio = decode_audio(path)
        self.audio = audio
        self.peaks = compute_peaks(audio, PEAK_COLUMNS)
        self._features = None
        self._tpl_cache.clear()
        self.auto_select(self.settings.default_length)
        return audio

    def set_selection(self, start: float, end: float) -> tuple[float, float]:
        """Приводит выбор к допустимым границам трека и длине фрагмента."""
        if self.audio is None:
            self.start, self.end = 0.0, 0.0
            return self.start, self.end
        dur = self.audio.duration
        start = max(0.0, min(start, dur))
        end = max(0.0, min(end, dur))
        if end < start:
            start, end = end, start
        length = min(max(end - start, min(MIN_SEGMENT_SEC, dur)), MAX_SEGMENT_SEC)
        if start + length > dur:
            start = max(0.0, dur - length)
        self.start, self.end = start, min(dur, start + length)
        return self.start, self.end

    def auto_select(self, length: float) -> tuple[float, float]:
        if self.audio is None:
            return 0.0, 0.0
        a, b = best_segment(self.audio, min(length, MAX_SEGMENT_SEC))
        return self.set_selection(a, b)

    @property
    def selection_length(self) -> float:
        return self.end - self.start

    # ---- предпросмотр -----------------------------------------------------
    def _preview_features(self) -> AudioFeatures:
        assert self.audio is not None
        key = (id(self.audio), round(self.start, 3), round(self.end, 3))
        if key != self._features_key or self._features is None:
            self._features = analyze_segment(self.audio.mono_float(self.start, self.end), self.audio.sample_rate, PREVIEW_FPS)
            self._features_key = key
            self._tpl_cache.clear()
        return self._features

    def _preview_template(self, template_id: str, width: int) -> VisualTemplate:
        features = self._preview_features()
        height = round(width * 16 / 9 / 2) * 2
        key = (template_id, width, json.dumps(self.visual.to_dict(), sort_keys=True))
        if key not in self._tpl_cache:
            if len(self._tpl_cache) >= 4:
                self._tpl_cache.clear()
            self._tpl_cache[key] = TEMPLATES[template_id](width, height, self.visual, features)
        return self._tpl_cache[key]

    def render_preview(self, template_id: str, t: float, width: int = 288) -> Image.Image:
        """Кадр предпросмотра в момент t (секунды от начала фрагмента)."""
        tpl = self._preview_template(template_id, width)
        return tpl.render(int(max(0.0, t) * PREVIEW_FPS))

    def write_preview_audio(self, offset: float = 0.0) -> Path | None:
        """WAV фрагмента (начиная с offset секунд) для прослушивания в приложении."""
        if self.audio is None:
            return None
        self._preview_counter += 1
        for old in self._tmp_dir.glob("preview_*.wav"):  # прошлые файлы уже не играют
            try:
                old.unlink()
            except OSError:
                pass
        path = self._tmp_dir / f"preview_{self._preview_counter}.wav"
        a = min(self.end - 0.1, self.start + max(0.0, offset))
        write_wav(path, fade_samples(self.audio.segment_int16(a, self.end), self.audio.sample_rate, 0.05, 0.1), self.audio.sample_rate)
        return path

    # ---- задание ----------------------------------------------------------
    def build_job(self) -> JobConfig:
        s = self.settings
        w, h = RESOLUTIONS.get(s.resolution, RESOLUTIONS["1080x1920"])
        return JobConfig(
            audio_path=self.audio.path if self.audio else "", start=self.start, end=self.end,
            templates=list(self.templates), visual=self.visual, output_dir=s.output_dir,
            width=w, height=h, fps=s.fps, quality=s.quality, fade_in=s.fade_in, fade_out=s.fade_out,
        )

    def cleanup(self) -> None:
        import shutil

        shutil.rmtree(self._tmp_dir, ignore_errors=True)
