"""Постоянные настройки приложения. Запись атомарная, повреждённый файл не затирается молча."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .config import FPS_CHOICES, QUALITY, RESOLUTIONS
from .paths import app_data_dir, default_output_dir

log = logging.getLogger(__name__)


@dataclass
class AppSettings:
    output_dir: str = ""
    resolution: str = "1080x1920"
    fps: int = 30
    quality: str = "balanced"
    fade_in: float = 0.3
    fade_out: float = 0.8
    default_length: float = 30.0
    open_folder_after: bool = True
    last_import_dir: str = ""
    last_preset_dir: str = ""
    window_geometry: str = ""
    visual: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = str(default_output_dir())

    @classmethod
    def from_dict(cls, data: object) -> "AppSettings":
        result = cls()
        if not isinstance(data, dict):
            return result
        for f in fields(cls):
            if f.name not in data:
                continue
            default = getattr(result, f.name)
            raw = data[f.name]
            try:
                if isinstance(default, bool):
                    value = bool(raw)
                elif isinstance(default, int):
                    value = int(raw)
                elif isinstance(default, float):
                    value = float(raw)
                elif isinstance(default, dict):
                    value = raw if isinstance(raw, dict) else {}
                else:
                    value = str(raw)
            except (TypeError, ValueError):
                continue
            setattr(result, f.name, value)
        if result.resolution not in RESOLUTIONS:
            result.resolution = "1080x1920"
        if result.fps not in FPS_CHOICES:
            result.fps = 30
        if result.quality not in QUALITY:
            result.quality = "balanced"
        result.fade_in = max(0.0, min(5.0, result.fade_in))
        result.fade_out = max(0.0, min(5.0, result.fade_out))
        result.default_length = max(1.0, min(180.0, result.default_length))
        if not result.output_dir:
            result.output_dir = str(default_output_dir())
        return result


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else app_data_dir() / "settings.json"

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            return AppSettings.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{int(time.time())}{self.path.suffix}")
            try:
                os.replace(self.path, backup)
                log.warning("Повреждённый файл настроек сохранён как %s (%s)", backup, exc)
            except OSError:
                log.warning("Не удалось сохранить копию повреждённых настроек: %s", exc)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
