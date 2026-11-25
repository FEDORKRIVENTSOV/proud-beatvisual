"""Виджет волны трека с выбором фрагмента мышью (перетаскивание краёв и всего фрагмента)."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from ..config import MAX_SEGMENT_SEC, MIN_SEGMENT_SEC
from . import theme

HANDLE_PX = 9


class WaveformView(tk.Canvas):
    def __init__(self, master, on_change: Callable[[float, float], None], height: int = 150) -> None:
        super().__init__(master, height=height, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.FIELD, cursor="hand2")
        self.on_change = on_change
        self.peaks = None
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.playhead: float | None = None
        self._mode: str | None = None
        self._anchor = 0.0
        self._grab = 0.0
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    # ---- данные -----------------------------------------------------------
    def set_audio(self, peaks, duration: float) -> None:
        self.peaks, self.duration = peaks, duration
        self.redraw()

    def set_selection(self, start: float, end: float) -> None:
        self.start, self.end = start, end
        self.redraw()

    def set_playhead(self, t: float | None) -> None:
        self.playhead = t
        self._draw_overlay()

    # ---- координаты -------------------------------------------------------
    def _x(self, t: float) -> float:
        w = max(1, self.winfo_width())
        return t / self.duration * w if self.duration else 0.0

    def _t(self, x: float) -> float:
        w = max(1, self.winfo_width())
        return max(0.0, min(self.duration, x / w * self.duration))

    # ---- отрисовка --------------------------------------------------------
    def redraw(self) -> None:
        self.delete("all")
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        if self.peaks is None or not self.duration:
            self.create_text(w / 2, h / 2, text="Импортируйте бит: Ctrl+O", fill=theme.MUTED, font=("Segoe UI", 11))
            return
        n = len(self.peaks)
        mid = h / 2
        for px in range(w):
            col = self.peaks[min(n - 1, int(px / w * n))]
            self.create_line(px, mid - float(col[1]) * mid * 0.92, px, mid - float(col[0]) * mid * 0.92 + 1, fill="#3a3a52", tags="wave")
        self._draw_overlay()

    def _draw_overlay(self) -> None:
        self.delete("sel")
        if self.peaks is None or not self.duration:
            return
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        n = len(self.peaks)
        mid = h / 2
        x0, x1 = int(self._x(self.start)), int(self._x(self.end))
        for px in range(max(0, x0), min(w, x1 + 1)):
            col = self.peaks[min(n - 1, int(px / w * n))]
            self.create_line(px, mid - float(col[1]) * mid * 0.92, px, mid - float(col[0]) * mid * 0.92 + 1, fill=theme.ACCENT, tags="sel")
        for x in (x0, x1):
            self.create_rectangle(x - 2, 0, x + 2, h, fill="#ffffff", outline="", tags="sel")
            self.create_rectangle(x - HANDLE_PX // 2, h / 2 - 16, x + HANDLE_PX // 2, h / 2 + 16, fill=theme.ACCENT, outline="#ffffff", tags="sel")
        if self.playhead is not None:
            px = self._x(self.start + self.playhead)
            self.create_line(px, 0, px, h, fill="#ff4d6d", width=2, tags="sel")

    # ---- мышь -------------------------------------------------------------
    def _press(self, event) -> None:
        if self.peaks is None or not self.duration:
            return
        self.focus_set()
        x0, x1 = self._x(self.start), self._x(self.end)
        if abs(event.x - x0) <= HANDLE_PX + 3:
            self._mode = "left"
        elif abs(event.x - x1) <= HANDLE_PX + 3:
            self._mode = "right"
        elif x0 < event.x < x1:
            self._mode, self._grab = "move", self._t(event.x) - self.start
        else:
            self._mode, self._anchor = "new", self._t(event.x)

    def _drag(self, event) -> None:
        if self._mode is None:
            return
        t = self._t(event.x)
        start, end = self.start, self.end
        if self._mode == "left":
            start = min(t, end - MIN_SEGMENT_SEC)
            start = max(start, end - MAX_SEGMENT_SEC, 0.0)
        elif self._mode == "right":
            end = max(t, start + MIN_SEGMENT_SEC)
            end = min(end, start + MAX_SEGMENT_SEC, self.duration)
        elif self._mode == "move":
            length = end - start
            start = max(0.0, min(self.duration - length, t - self._grab))
            end = start + length
        else:
            start, end = sorted((self._anchor, t))
            if end - start < MIN_SEGMENT_SEC:
                end = min(self.duration, start + MIN_SEGMENT_SEC)
                start = max(0.0, end - MIN_SEGMENT_SEC)
            if end - start > MAX_SEGMENT_SEC:
                end = start + MAX_SEGMENT_SEC
        self.start, self.end = start, end
        self._draw_overlay()
        self.on_change(start, end)

    def _release(self, _event) -> None:
        self._mode = None
