"""Реестр визуальных шаблонов."""
from __future__ import annotations

from .base import VisualTemplate
from .minimal_type import MinimalType
from .neon_wave import NeonWave
from .spectrum_bars import SpectrumBars

TEMPLATES: dict[str, type[VisualTemplate]] = {cls.id: cls for cls in (NeonWave, SpectrumBars, MinimalType)}


def get_template(template_id: str) -> type[VisualTemplate]:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise KeyError(f"Неизвестный шаблон: {template_id}") from exc
