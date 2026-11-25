"""Minimal Type: крупная типографика по центру и тонкое пульсирующее кольцо."""
from __future__ import annotations

import math

import numpy as np

from .base import Palette, VisualTemplate

N_TICKS = 72


class MinimalType(VisualTemplate):
    id = "minimal_type"
    name = "Minimal Type"
    description = "Минимализм: огромный заголовок, кольцо пульсирует в такт баса."
    palette = Palette("#FFFFFF", "#8C8C98", "#0A0A0A", "#16161A")
    text_region = (0.30, 0.62)
    title_size = 170
    subtitle_size = 48
    title_lines = 4
    text_width = 0.56

    def layout(self) -> None:
        cy = self.h * 0.46
        half = self.w * 0.50
        self.center_abs = (self.w / 2, cy)
        self.vis_rect = (0, int(cy - half), self.w, int(cy + half))

    def draw_visual(self, d, i, lw, lh):
        s = self.s
        cx, cy = lw / 2, lh / 2
        bass = float(self.gain(self.f.bass[i]))
        level = float(self.gain(self.f.level[i]))
        radius = self.w * 0.34 * (1.0 + 0.07 * bass)
        width = max(2, int(3 * s))
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=self.scale_color(self.accent, 0.35 + 0.65 * bass), width=width)
        inner = self.w * 0.30 * (1.0 + 0.03 * level)
        d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), outline=self.scale_color(self.secondary, 0.45), width=max(1, int(2 * s)))
        bands = self.gain(self.f.bands[i])
        usable = int(len(bands) * 0.8)
        half = N_TICKS // 2
        for k in range(N_TICKS):
            j = k if k < half else N_TICKS - 1 - k
            v = float(bands[min(usable - 1, int(j / half * usable))])
            angle = -math.pi / 2 + 2 * math.pi * k / N_TICKS
            r0 = radius + 12 * s
            r1 = r0 + (6 + 70 * v) * s
            d.line((cx + math.cos(angle) * r0, cy + math.sin(angle) * r0, cx + math.cos(angle) * r1, cy + math.sin(angle) * r1),
                   fill=self.mix(self.secondary, self.accent, v), width=max(2, int(5 * s)))
