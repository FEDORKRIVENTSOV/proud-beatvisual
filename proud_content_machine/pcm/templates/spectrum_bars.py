"""Spectrum Bars: зеркальные столбцы спектра с пиковыми точками."""
from __future__ import annotations

import numpy as np

from .base import Palette, VisualTemplate


class SpectrumBars(VisualTemplate):
    id = "spectrum_bars"
    name = "Spectrum Bars"
    description = "Зеркальные столбцы спектра с градиентом и пиковыми точками."
    palette = Palette("#FF3D6E", "#FFB02E", "#0B0A12", "#1A1024")
    text_region = (0.15, 0.34)

    def layout(self) -> None:
        self.vis_rect = (0, int(self.h * 0.36), self.w, int(self.h * 0.68))

    def prepare(self) -> None:
        bands = self.gain(self.f.bands)
        peaks = np.zeros_like(bands)
        held = np.zeros(bands.shape[1], dtype=np.float32)
        decay = 0.9 / self.fps
        for k in range(len(bands)):
            held = np.maximum(bands[k], held - decay)
            peaks[k] = held
        self.bands_g, self.peaks_g = bands, peaks
        n = bands.shape[1]
        self.colors = [self.mix(self.accent, self.secondary, j / max(1, n - 1)) for j in range(n)]

    def draw_visual(self, d, i, lw, lh):
        s = self.s
        n = self.bands_g.shape[1]
        total = lw * 0.88
        slot = total / n
        bar_w = max(2.0, slot * 0.62)
        x0 = (lw - total) / 2
        cy = lh / 2
        max_half = lh * 0.46
        for j in range(n):
            v = float(self.bands_g[i, j])
            half = max(3 * s, v * max_half)
            cx = x0 + slot * (j + 0.5)
            color = self.scale_color(self.colors[j], 0.55 + 0.45 * v)
            d.rounded_rectangle((cx - bar_w / 2, cy - half, cx + bar_w / 2, cy + half), radius=bar_w / 2, fill=color)
            p = max(float(self.peaks_g[i, j]) * max_half, half) + 12 * s
            if p < lh / 2 - 2 * s:
                r = max(1.5, bar_w * 0.22)
                for sign in (-1, 1):
                    d.ellipse((cx - r, cy + sign * p - r, cx + r, cy + sign * p + r), fill=self.colors[j])
