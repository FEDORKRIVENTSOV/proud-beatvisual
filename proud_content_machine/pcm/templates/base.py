"""Базовый класс шаблона: фон, заголовок, свечение, прогресс. Вся вёрстка не зависит от разрешения."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..audio import AudioFeatures
from ..config import VisualConfig, hex_to_rgb
from ..fonts import load_font


@dataclass(frozen=True)
class Palette:
    accent: str
    secondary: str
    bg_top: str
    bg_bottom: str


@dataclass
class TextBlock:
    rgb: Image.Image
    mask: Image.Image

    @property
    def w(self) -> int:
        return self.rgb.width

    @property
    def h(self) -> int:
        return self.rgb.height


def _wrap(text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _hard_split(line: str, font, max_width: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for ch in line:
        if font.getlength(current + ch) > max_width and current:
            parts.append(current)
            current = ch
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


def render_text_block(text, font_key, font_path, size, max_width, max_height, max_lines, color, shadow) -> TextBlock | None:
    """Рисует многострочный центрированный текст с мягкой тенью; шрифт уменьшается, пока всё не поместится."""
    text = " ".join(text.split())
    if not text:
        return None
    min_size = max(10.0, size * 0.3)
    cur = float(size)
    while True:
        font = load_font(font_key, font_path, int(cur))
        lines = _wrap(text, font, max_width)
        ascent, descent = font.getmetrics()
        line_h = int((ascent + descent) * 1.08)
        fits = len(lines) <= max_lines and all(font.getlength(l) <= max_width for l in lines) and line_h * len(lines) <= max_height
        if fits or cur <= min_size:
            break
        cur *= 0.93
    if not fits:
        lines = [part for l in lines for part in (_hard_split(l, font, max_width) if font.getlength(l) > max_width else [l])]
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip()[:-1] + "…"
    width = max(int(max(font.getlength(l) for l in lines)), 1)
    height = line_h * len(lines)
    pad = int(shadow * 3) + 2
    mask = Image.new("L", (width + 2 * pad, height + 2 * pad), 0)
    draw = ImageDraw.Draw(mask)
    for i, line in enumerate(lines):
        draw.text((pad + width / 2, pad + i * line_h), line, font=font, fill=255, anchor="ma")
    shadow_mask = mask.filter(ImageFilter.GaussianBlur(max(1.0, shadow))).point([int(v * 0.75) for v in range(256)])
    rgb = Image.new("RGB", mask.size, (0, 0, 0))
    rgb.paste(color, mask=mask)
    return TextBlock(rgb=rgb, mask=ImageChops.lighter(mask, shadow_mask))


def _ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class VisualTemplate:
    id = "base"
    name = "Base"
    description = ""
    palette = Palette("#FFFFFF", "#AAAAAA", "#000000", "#111111")

    # область для текстовой группы (доли высоты), размеры шрифтов при ширине 1080
    text_region = (0.15, 0.33)
    title_size = 118
    subtitle_size = 44
    title_lines = 3
    text_width = 0.84

    def __init__(self, width: int, height: int, config: VisualConfig, features: AudioFeatures) -> None:
        self.w, self.h = int(width), int(height)
        self.s = self.w / 1080.0
        self.cfg = config
        self.f = features
        self.fps = features.fps
        self.n_frames = features.n_frames
        pal = self.palette
        if config.use_template_palette:
            self.accent = hex_to_rgb(pal.accent)
            self.secondary = hex_to_rgb(pal.secondary)
            self.bg_top = hex_to_rgb(pal.bg_top)
            self.bg_bottom = hex_to_rgb(pal.bg_bottom)
        else:
            self.accent = hex_to_rgb(config.accent)
            self.secondary = hex_to_rgb(config.secondary)
            self.bg_top = hex_to_rgb(config.bg_top)
            self.bg_bottom = hex_to_rgb(config.bg_bottom)
        self.text_color = hex_to_rgb(config.text_color)
        self.sens = config.sensitivity
        self.vis_rect = (0, 0, self.w, self.h)
        self.title: TextBlock | None = None
        self.subtitle: TextBlock | None = None
        self.title_xy = (0, 0)
        self.subtitle_xy = (0, 0)
        self.bg = self._build_background()
        self.layout()
        self._build_text()
        self.prepare()

    # ---- хуки для шаблонов ------------------------------------------------
    def layout(self) -> None:
        """Задаёт self.vis_rect и при необходимости self.text_region."""

    def prepare(self) -> None:
        """Дополнительные вычисления один раз на весь ролик."""

    def draw_visual(self, d: ImageDraw.ImageDraw, i: int, lw: int, lh: int) -> None:
        raise NotImplementedError

    # ---- утилиты ----------------------------------------------------------
    def gain(self, values):
        return np.clip(values, 0.0, 1.0) ** (1.0 / self.sens)

    def mix(self, a, b, t: float) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, float(t)))
        return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))

    def scale_color(self, color, k: float) -> tuple[int, int, int]:
        k = max(0.0, min(1.0, float(k)))
        return tuple(int(c * k) for c in color)

    # ---- фон --------------------------------------------------------------
    def _build_background(self) -> Image.Image:
        cfg = self.cfg
        mode = cfg.bg_mode
        if mode == "image" and not (cfg.bg_image and Path(cfg.bg_image).is_file()):
            mode = "gradient"  # файла нет: запасной градиентный фон
        arr = None
        if mode == "image":
            try:
                with Image.open(cfg.bg_image) as src:
                    src = src.convert("RGB")
                scale = max(self.w / src.width, self.h / src.height)
                resized = src.resize((max(self.w, round(src.width * scale)), max(self.h, round(src.height * scale))), Image.LANCZOS)
                left, top = (resized.width - self.w) // 2, (resized.height - self.h) // 2
                base = resized.crop((left, top, left + self.w, top + self.h))
                arr = np.asarray(base, dtype=np.float32) * (1.0 - cfg.bg_dim)
            except (OSError, ValueError):
                arr = None  # битая картинка: запасной градиент
        if arr is None:
            t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)[:, None, None]
            top = np.array(self.bg_top, dtype=np.float32)[None, None, :]
            bottom = np.array(self.bg_bottom if mode == "gradient" else self.bg_top, dtype=np.float32)[None, None, :]
            arr = np.broadcast_to(top + (bottom - top) * t, (self.h, self.w, 3)).copy()
        # мягкая виньетка для глубины
        sh, sw = max(2, self.h // 8), max(2, self.w // 8)
        yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
        dist = np.sqrt(((xx / (sw - 1) - 0.5) * 2) ** 2 + ((yy / (sh - 1) - 0.5) * 2) ** 2)
        vig = Image.fromarray(np.uint8(np.clip(1.0 - 0.28 * np.clip(dist - 0.35, 0, 1), 0, 1) * 255), "L")
        vig = np.asarray(vig.resize((self.w, self.h), Image.BILINEAR), dtype=np.float32)[:, :, None] / 255.0
        return Image.fromarray(np.uint8(np.clip(arr * vig, 0, 255)), "RGB")

    # ---- текст ------------------------------------------------------------
    def _build_text(self) -> None:
        cfg, s = self.cfg, self.s
        max_w = int(self.w * self.text_width)
        top = int(self.h * self.text_region[0])
        bottom = int(self.h * self.text_region[1])
        region_h = bottom - top
        gap = int(24 * s)
        shadow = max(2.0, 6 * s)
        sub = None
        if cfg.subtitle.strip():
            sub = render_text_block(cfg.subtitle, cfg.font_key, cfg.font_path, self.subtitle_size * s, max_w,
                                    int(region_h * 0.3), 2, self.accent_text(), shadow)
        sub_h = (sub.h + gap) if sub else 0
        text = cfg.title.upper() if cfg.title_caps else cfg.title
        title = render_text_block(text, cfg.font_key, cfg.font_path, self.title_size * s * cfg.title_scale, max_w,
                                  max(10, region_h - sub_h), self.title_lines, self.text_color, shadow)
        total = (title.h if title else 0) + sub_h
        y = top + max(0, (region_h - total) // 2)
        if title:
            self.title, self.title_xy = title, ((self.w - title.w) // 2, y)
            y += title.h + gap
        if sub:
            self.subtitle, self.subtitle_xy = sub, ((self.w - sub.w) // 2, y)

    def accent_text(self) -> tuple[int, int, int]:
        return self.mix(self.accent, (255, 255, 255), 0.35)

    def _paste_text(self, img: Image.Image, block: TextBlock | None, xy, i: int, delay: float) -> None:
        if block is None:
            return
        t = i / self.fps
        alpha, dy = 1.0, 0
        if self.cfg.title_animation:
            e = _ease_out((t - delay) / 0.7)
            alpha, dy = e, int((1 - e) * 24 * self.s)
        if alpha <= 0.0:
            return
        mask = block.mask if alpha >= 0.999 else block.mask.point([int(v * alpha) for v in range(256)])
        img.paste(block.rgb, (xy[0], xy[1] + dy), mask)

    def _draw_progress(self, img: Image.Image, i: int) -> None:
        if not self.cfg.show_progress:
            return
        s = self.s
        x0, x1 = int(self.w * 0.15), int(self.w * 0.85)
        y = int(self.h * 0.855)
        th = max(2, int(6 * s))
        frac = (i + 1) / max(1, self.n_frames)
        d = ImageDraw.Draw(img)
        track = self.mix(self.bg_bottom, (255, 255, 255), 0.22)
        d.rounded_rectangle((x0, y, x1, y + th), radius=th // 2, fill=track)
        fill_x = x0 + int((x1 - x0) * frac)
        if fill_x - x0 >= th:
            d.rounded_rectangle((x0, y, fill_x, y + th), radius=th // 2, fill=self.accent)

    # ---- кадр -------------------------------------------------------------
    def _glow(self, layer: Image.Image) -> Image.Image:
        lw, lh = layer.size
        small = layer.resize((max(1, lw // 4), max(1, lh // 4)), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(max(1.0, 5.0 * self.s)))
        k = 0.6 + 1.8 * self.cfg.glow_strength
        big = small.resize((lw, lh), Image.BILINEAR)
        return big.point([min(255, int(v * k)) for v in range(256)] * 3)

    def render(self, i: int) -> Image.Image:
        i = max(0, min(self.n_frames - 1, int(i)))
        img = self.bg.copy()
        x0, y0, x1, y1 = self.vis_rect
        lw, lh = x1 - x0, y1 - y0
        layer = Image.new("RGB", (lw, lh))
        self.draw_visual(ImageDraw.Draw(layer), i, lw, lh)
        region = img.crop(self.vis_rect)
        if self.cfg.glow and self.cfg.glow_strength > 0:
            region = ImageChops.screen(region, self._glow(layer))
        region = ImageChops.screen(region, layer)
        img.paste(region, (x0, y0))
        self._paste_text(img, self.title, self.title_xy, i, 0.0)
        self._paste_text(img, self.subtitle, self.subtitle_xy, i, 0.25)
        self._draw_progress(img, i)
        return img
