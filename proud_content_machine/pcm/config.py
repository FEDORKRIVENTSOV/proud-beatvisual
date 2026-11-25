"""Конфигурация визуала и задания на экспорт, валидация."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .fonts import FONT_KEYS
from .paths import check_writable

MIN_SEGMENT_SEC = 1.0
MAX_SEGMENT_SEC = 180.0
RESOLUTIONS = {"1080x1920": (1080, 1920), "720x1280": (720, 1280)}
FPS_CHOICES = (24, 25, 30, 60)
# качество -> (CRF, пресет x264)
QUALITY = {"draft": (28, "ultrafast"), "balanced": (21, "veryfast"), "high": (17, "medium")}
QUALITY_LABELS = {"draft": "Черновик (быстро)", "balanced": "Баланс", "high": "Высокое"}
BG_MODES = ("gradient", "solid", "image")

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_hex_color(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX.match(value))


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class VisualConfig:
    title: str = ""
    subtitle: str = ""
    title_caps: bool = False
    use_template_palette: bool = True
    accent: str = "#00F0FF"
    secondary: str = "#FF2BD6"
    bg_mode: str = "gradient"
    bg_top: str = "#07060F"
    bg_bottom: str = "#1A0B2E"
    bg_image: str = ""
    bg_dim: float = 0.55
    font_key: str = "auto"
    font_path: str = ""
    text_color: str = "#FFFFFF"
    title_scale: float = 1.0
    sensitivity: float = 1.0
    glow: bool = True
    glow_strength: float = 0.7
    show_progress: bool = True
    title_animation: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "VisualConfig":
        """Безопасно собирает конфиг: неверные типы и значения заменяются значениями по умолчанию."""
        base = cls()
        if not isinstance(data, dict):
            return base
        for f in fields(cls):
            if f.name not in data:
                continue
            raw = data[f.name]
            default = getattr(base, f.name)
            try:
                if isinstance(default, bool):
                    value = bool(raw)
                elif isinstance(default, float):
                    value = float(raw)
                else:
                    value = str(raw)
            except (TypeError, ValueError):
                continue
            setattr(base, f.name, value)
        for name in ("accent", "secondary", "bg_top", "bg_bottom", "text_color"):
            if not is_hex_color(getattr(base, name)):
                setattr(base, name, getattr(cls(), name))
        if base.bg_mode not in BG_MODES:
            base.bg_mode = "gradient"
        if base.font_key not in FONT_KEYS:
            base.font_key = "auto"
        base.bg_dim = _clamp(base.bg_dim, 0.0, 0.9)
        base.title_scale = _clamp(base.title_scale, 0.5, 1.6)
        base.sensitivity = _clamp(base.sensitivity, 0.4, 2.5)
        base.glow_strength = _clamp(base.glow_strength, 0.0, 1.0)
        return base


@dataclass
class JobConfig:
    audio_path: str = ""
    start: float = 0.0
    end: float = 0.0
    templates: list[str] = field(default_factory=list)
    visual: VisualConfig = field(default_factory=VisualConfig)
    output_dir: str = ""
    width: int = 1080
    height: int = 1920
    fps: int = 30
    quality: str = "balanced"
    fade_in: float = 0.3
    fade_out: float = 0.8

    @property
    def duration(self) -> float:
        return self.end - self.start


def validate_job(job: JobConfig, audio_duration: float | None = None) -> list[str]:
    """Возвращает список ошибок на русском. Пустой список означает, что задание корректно."""
    from .templates import TEMPLATES  # отложенный импорт: шаблоны зависят от этого модуля

    errors: list[str] = []
    if not job.audio_path or not Path(job.audio_path).is_file():
        errors.append("Не выбран аудиофайл (бит).")
    if job.duration < MIN_SEGMENT_SEC:
        errors.append(f"Фрагмент слишком короткий: минимум {MIN_SEGMENT_SEC:g} с.")
    if job.duration > MAX_SEGMENT_SEC:
        errors.append(f"Фрагмент слишком длинный: максимум {MAX_SEGMENT_SEC:g} с.")
    if audio_duration is not None and (job.start < 0 or job.end > audio_duration + 0.01):
        errors.append("Фрагмент выходит за границы трека.")
    if not job.visual.title.strip():
        errors.append("Укажите название.")
    unique = list(dict.fromkeys(job.templates))
    if not 1 <= len(unique) <= 3:
        errors.append("Выберите от одного до трёх визуальных шаблонов.")
    for template_id in unique:
        if template_id not in TEMPLATES:
            errors.append(f"Неизвестный шаблон: {template_id}")
    if job.visual.bg_mode == "image" and not Path(job.visual.bg_image).is_file():
        errors.append("Фоновое изображение не найдено. Выберите файл или другой режим фона.")
    if job.visual.font_key == "custom" and not Path(job.visual.font_path).is_file():
        errors.append("Файл своего шрифта не найден.")
    if job.width <= 0 or job.height <= 0 or job.width % 2 or job.height % 2:
        errors.append("Размер видео должен состоять из чётных положительных чисел.")
    if job.fps not in FPS_CHOICES:
        errors.append(f"Недопустимая частота кадров: {job.fps}.")
    if job.quality not in QUALITY:
        errors.append("Неизвестный пресет качества.")
    if not 0 <= job.fade_in <= 5 or not 0 <= job.fade_out <= 5:
        errors.append("Длительность fade должна быть от 0 до 5 секунд.")
    if not job.output_dir:
        errors.append("Не указана папка для результата.")
    else:
        problem = check_writable(job.output_dir)
        if problem:
            errors.append(problem)
    return errors
