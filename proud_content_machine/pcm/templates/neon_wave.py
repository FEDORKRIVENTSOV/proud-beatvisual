"""Neon Wave: неоновая осциллограмма с двумя линиями."""
from __future__ import annotations

import numpy as np

from .base import Palette, VisualTemplate

N_POINTS = 200


class NeonWave(VisualTemplate):
    id = "neon_wave"
    name = "Neon Wave"
    description = "Неоновая осциллограмма: две светящиеся линии реагируют на звук."
    palette = Palette("#00F0FF", "#FF2BD6", "#07060F", "#1B0A33")
    text_region = (0.15, 0.34)

    def layout(self) -> None:
        self.vis_rect = (0, int(self.h * 0.38), self.w, int(self.h * 0.66))
        x = np.linspace(0.0, 1.0, N_POINTS)
        self.taper = np.sin(np.pi * x) ** 0.9

    def draw_visual(self, d, i, lw, lh):
        s = self.s
        cy = lh / 2
        xs = np.linspace(lw * 0.06, lw * 0.94, N_POINTS)
        level = float(self.gain(self.f.level[i]))
        amp = lh * 0.46 * (0.30 + 0.70 * level)
        d.line([(lw * 0.06, cy), (lw * 0.94, cy)], fill=self.scale_color(self.accent, 0.28), width=max(1, int(3 * s)))
        for shift, color, width in ((0.012, self.secondary, 5), (0.0, self.accent, 7)):
            wave = self.f.wave_window(max(0, i), N_POINTS) if shift == 0 else self.f.wave_window(i, N_POINTS, 0.03 + shift)
            y = cy - np.clip(wave * self.sens, -1, 1) * self.taper * amp
            d.line(list(zip(xs.tolist(), y.tolist())), fill=color, width=max(2, int(width * s)), joint="curve")
        r = int((14 + 14 * level) * s)
        d.ellipse((lw / 2 - r, cy - r, lw / 2 + r, cy + r), outline=self.mix(self.accent, self.secondary, 0.5), width=max(2, int(3 * s)))
