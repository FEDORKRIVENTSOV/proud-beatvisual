"""Главное окно PROUD CONTENT MACHINE."""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import ImageTk

from .. import APP_NAME, __version__
from ..config import BG_MODES, VisualConfig, validate_job
from ..exporter import ExportCancelled, ExportError, ExportProgress, ValidationError, export_job
from ..fonts import FONTS
from ..paths import format_time, parse_time
from ..session import Session
from ..settings import SettingsStore
from ..templates import TEMPLATES
from . import theme
from .settings_dialog import SettingsDialog
from .waveform import WaveformView

try:  # воспроизведение WAV встроено в Windows
    import winsound
except ImportError:  # другие ОС: предпросмотр без звука
    winsound = None

log = logging.getLogger(__name__)

BG_LABELS = {"gradient": "Градиент", "solid": "Сплошной цвет", "image": "Изображение"}
AUDIO_TYPES = [("Аудио", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma *.aiff *.opus"), ("Все файлы", "*.*")]
PREVIEW_W, PREVIEW_H = 288, 512


class PCMApp(tk.Tk):
    def __init__(self, initial_audio: str | None = None) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {__version__}")
        self.minsize(1120, 780)
        theme.apply_theme(self)
        self.store = SettingsStore()
        self.settings = self.store.load()
        self.session = Session(self.settings)
        self._queue: queue.Queue = queue.Queue()
        self._cancel = threading.Event()
        self._export_thread: threading.Thread | None = None
        self._loading = False
        self._building = True
        self._playing = False
        self._play_started = 0.0
        self._play_offset = 0.0
        self._preview_t = 0.0
        self._setting_scale = False
        self._preview_job = None
        self._photo = None
        self.report_callback_exception = self._report_exception

        self._build_vars()
        self._build_menu()
        self._build_ui()
        self._bind_keys()
        if self.settings.window_geometry:
            try:
                self.geometry(self.settings.window_geometry)
            except tk.TclError:
                pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._building = False
        self._on_visual_change()
        self._on_templates_change()
        self.after(100, self._poll_queue)
        if initial_audio:
            self.after(300, lambda: self.load_audio(initial_audio))

    # ================= переменные =================
    def _build_vars(self) -> None:
        v = self.session.visual
        self.title_var = tk.StringVar(value="")
        self.subtitle_var = tk.StringVar(value=v.subtitle)
        self.caps_var = tk.BooleanVar(value=v.title_caps)
        self.palette_var = tk.BooleanVar(value=v.use_template_palette)
        self.color_vars = {k: tk.StringVar(value=getattr(v, k)) for k in ("accent", "secondary", "bg_top", "bg_bottom", "text_color")}
        self.bg_mode_var = tk.StringVar(value=BG_LABELS[v.bg_mode])
        self.bg_image_var = tk.StringVar(value=v.bg_image)
        self.bg_dim_var = tk.DoubleVar(value=v.bg_dim)
        self.font_var = tk.StringVar(value=FONTS[v.font_key][0])
        self.font_path_var = tk.StringVar(value=v.font_path)
        self.title_scale_var = tk.DoubleVar(value=v.title_scale)
        self.sens_var = tk.DoubleVar(value=v.sensitivity)
        self.glow_var = tk.BooleanVar(value=v.glow)
        self.glow_strength_var = tk.DoubleVar(value=v.glow_strength)
        self.progress_var = tk.BooleanVar(value=v.show_progress)
        self.anim_var = tk.BooleanVar(value=v.title_animation)
        self.tpl_vars = {tid: tk.BooleanVar(value=(tid in self.session.templates)) for tid in TEMPLATES}
        self.preview_tpl_var = tk.StringVar(value=TEMPLATES[self.session.templates[0]].name)
        self.start_var = tk.StringVar(value="0:00.000")
        self.end_var = tk.StringVar(value="0:00.000")
        self.length_var = tk.StringVar(value="Длина: 0.0 с")
        self.file_var = tk.StringVar(value="Файл не выбран")
        self.info_var = tk.StringVar(value="")
        self.out_var = tk.StringVar(value=self.settings.output_dir)
        self.status_var = tk.StringVar(value="Готово. Импортируйте бит (Ctrl+O).")
        self.time_var = tk.StringVar(value="0:00.0 / 0:00.0")
        for var in (self.title_var, self.subtitle_var, self.caps_var, self.palette_var, self.bg_mode_var, self.bg_image_var,
                    self.bg_dim_var, self.font_var, self.font_path_var, self.title_scale_var, self.sens_var, self.glow_var,
                    self.glow_strength_var, self.progress_var, self.anim_var, *self.color_vars.values()):
            var.trace_add("write", self._on_visual_change)
        for var in self.tpl_vars.values():
            var.trace_add("write", self._on_templates_change)
        self.out_var.trace_add("write", lambda *_: setattr(self.settings, "output_dir", self.out_var.get().strip()))

    # ================= меню =================
    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Импорт бита…  (Ctrl+O)", command=self.import_audio)
        file_menu.add_command(label="Сохранить пресет визуала…", command=self.save_preset)
        file_menu.add_command(label="Загрузить пресет визуала…", command=self.load_preset)
        file_menu.add_separator()
        file_menu.add_command(label="Настройки…", command=self.open_settings)
        file_menu.add_command(label="Открыть папку результата", command=self.open_output_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_close)
        bar.add_cascade(label="Файл", menu=file_menu)
        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="Горячие клавиши", command=self._show_keys)
        help_menu.add_command(label="О программе", command=self._show_about)
        bar.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=bar)

    # ================= интерфейс =================
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main = ttk.Frame(self, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        self.nb = ttk.Notebook(main)
        self.nb.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_tab_beat()
        self._build_tab_text()
        self._build_tab_visual()
        self._build_preview(main)
        self._build_bottom()

    def _build_tab_beat(self) -> None:
        tab = ttk.Frame(self.nb, padding=12)
        tab.columnconfigure(0, weight=1)
        self.nb.add(tab, text="1. Бит и фрагмент")
        top = ttk.Frame(tab)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Button(top, text="Импортировать бит…", style="Accent.TButton", command=self.import_audio).grid(row=0, column=0, padx=(0, 12))
        ttk.Label(top, textvariable=self.file_var, style="Title.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(tab, textvariable=self.info_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 8))
        self.wave = WaveformView(tab, self._on_wave_change)
        self.wave.grid(row=2, column=0, sticky="ew")
        ttk.Label(tab, text="Перетащите края выделения или весь фрагмент. Клик вне выделения создаёт новое.", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 10))
        row = ttk.Frame(tab)
        row.grid(row=4, column=0, sticky="w")
        ttk.Label(row, text="Начало").grid(row=0, column=0, padx=(0, 6))
        e1 = ttk.Entry(row, textvariable=self.start_var, width=10)
        e1.grid(row=0, column=1)
        ttk.Label(row, text="Конец").grid(row=0, column=2, padx=(16, 6))
        e2 = ttk.Entry(row, textvariable=self.end_var, width=10)
        e2.grid(row=0, column=3)
        for entry in (e1, e2):
            entry.bind("<Return>", lambda _e: self._apply_entries())
            entry.bind("<FocusOut>", lambda _e: self._apply_entries())
        ttk.Label(row, textvariable=self.length_var, style="Muted.TLabel").grid(row=0, column=4, padx=16)
        quick = ttk.Frame(tab)
        quick.grid(row=5, column=0, sticky="w", pady=(12, 0))
        ttk.Label(quick, text="Длина:").grid(row=0, column=0, padx=(0, 8))
        for k, length in enumerate((15, 30, 45, 60)):
            ttk.Button(quick, text=f"{length} с", width=6, command=lambda n=length: self._set_length(n)).grid(row=0, column=k + 1, padx=3)
        ttk.Button(quick, text="Лучший фрагмент", command=self._auto_select).grid(row=0, column=6, padx=(16, 3))
        ttk.Button(quick, text="▶ Слушать / стоп  (Пробел)", command=self.toggle_play).grid(row=0, column=7, padx=3)

    def _build_tab_text(self) -> None:
        tab = ttk.Frame(self.nb, padding=12)
        tab.columnconfigure(1, weight=1)
        self.nb.add(tab, text="2. Название и шаблоны")
        ttk.Label(tab, text="Название *").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(tab, textvariable=self.title_var, font=("Segoe UI", 13)).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(tab, text="Подзаголовок").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(tab, textvariable=self.subtitle_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(tab, text="ЗАГЛАВНЫЕ БУКВЫ", variable=self.caps_var).grid(row=2, column=1, sticky="w")
        box = ttk.LabelFrame(tab, text="Визуальные шаблоны (от 1 до 3, на каждый будет отдельный MP4)", padding=10)
        box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        for k, (tid, cls) in enumerate(TEMPLATES.items()):
            ttk.Checkbutton(box, text=cls.name, variable=self.tpl_vars[tid]).grid(row=k, column=0, sticky="w", pady=4)
            ttk.Label(box, text=cls.description, style="Muted.TLabel").grid(row=k, column=1, sticky="w", padx=14)

    def _slider(self, parent, row: int, label: str, var: tk.DoubleVar, lo: float, hi: float) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Scale(parent, from_=lo, to=hi, variable=var, length=220).grid(row=row, column=1, sticky="w", padx=8)
        shown = tk.StringVar(value=f"{var.get():.2f}")
        var.trace_add("write", lambda *_: shown.set(f"{var.get():.2f}"))
        ttk.Label(parent, textvariable=shown, width=5, style="Muted.TLabel").grid(row=row, column=2, sticky="w")

    def _color_button(self, parent, row: int, label: str, key: str, col: int = 0) -> tk.Button:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", pady=4)
        btn = tk.Button(parent, text="", width=6, relief="flat", bg=self.color_vars[key].get(), activebackground=self.color_vars[key].get(),
                        command=lambda k=key: self._pick_color(k))
        btn.grid(row=row, column=col + 1, sticky="w", padx=8)
        self.color_vars[key].trace_add("write", lambda *_a, b=btn, k=key: b.configure(bg=self.color_vars[k].get(), activebackground=self.color_vars[k].get()))
        return btn

    def _build_tab_visual(self) -> None:
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="3. Визуал")
        ttk.Checkbutton(tab, text="Использовать палитру шаблона (рекомендуется)", variable=self.palette_var).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        self._palette_buttons = [
            self._color_button(tab, 1, "Основной цвет", "accent"),
            self._color_button(tab, 2, "Второй цвет", "secondary"),
            self._color_button(tab, 3, "Фон: верх", "bg_top"),
            self._color_button(tab, 4, "Фон: низ", "bg_bottom"),
        ]
        self._color_button(tab, 5, "Цвет текста", "text_color")
        ttk.Label(tab, text="Фон").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Combobox(tab, textvariable=self.bg_mode_var, values=list(BG_LABELS.values()), state="readonly", width=18).grid(row=6, column=1, sticky="w", padx=8)
        ttk.Button(tab, text="Выбрать картинку…", command=self._pick_bg_image).grid(row=6, column=2, sticky="w")
        ttk.Label(tab, textvariable=self.bg_image_var, style="Muted.TLabel", width=34).grid(row=7, column=0, columnspan=4, sticky="w")
        self._slider(tab, 8, "Затемнение картинки", self.bg_dim_var, 0.0, 0.9)
        ttk.Label(tab, text="Шрифт").grid(row=9, column=0, sticky="w", pady=6)
        ttk.Combobox(tab, textvariable=self.font_var, values=[f[0] for f in FONTS.values()], state="readonly", width=28).grid(row=9, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Button(tab, text="Файл шрифта…", command=self._pick_font).grid(row=9, column=3, sticky="w")
        self._slider(tab, 10, "Размер заголовка", self.title_scale_var, 0.5, 1.6)
        self._slider(tab, 11, "Чувствительность", self.sens_var, 0.4, 2.5)
        self._slider(tab, 12, "Сила свечения", self.glow_strength_var, 0.0, 1.0)
        checks = ttk.Frame(tab)
        checks.grid(row=13, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(checks, text="Свечение", variable=self.glow_var).grid(row=0, column=0, padx=(0, 14))
        ttk.Checkbutton(checks, text="Полоса прогресса", variable=self.progress_var).grid(row=0, column=1, padx=(0, 14))
        ttk.Checkbutton(checks, text="Анимация появления текста", variable=self.anim_var).grid(row=0, column=2)
        presets = ttk.Frame(tab)
        presets.grid(row=14, column=0, columnspan=4, sticky="w", pady=(16, 0))
        ttk.Button(presets, text="Сохранить пресет…", command=self.save_preset).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(presets, text="Загрузить пресет…", command=self.load_preset).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(presets, text="Сбросить визуал", command=self.reset_visual).grid(row=0, column=2)

    def _build_preview(self, main) -> None:
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="n")
        ttk.Label(right, text="Предпросмотр", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.preview_canvas = tk.Canvas(right, width=PREVIEW_W, height=PREVIEW_H, bg="#000000", highlightthickness=1, highlightbackground=theme.FIELD)
        self.preview_canvas.grid(row=1, column=0, pady=6)
        self.preview_canvas.bind("<Button-1>", lambda _e: self.preview_canvas.focus_set())
        self.preview_canvas.bind("<space>", lambda _e: self.toggle_play())
        self.wave.bind("<space>", lambda _e: self.toggle_play())
        self.preview_combo = ttk.Combobox(right, textvariable=self.preview_tpl_var, state="readonly", width=24)
        self.preview_combo.grid(row=2, column=0, sticky="ew")
        self.preview_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_preview_template_picked())
        self.scale = ttk.Scale(right, from_=0.0, to=1.0, command=self._on_scrub)
        self.scale.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        bar = ttk.Frame(right)
        bar.grid(row=4, column=0, sticky="ew", pady=4)
        self.play_btn = ttk.Button(bar, text="▶ Играть", command=self.toggle_play)
        self.play_btn.grid(row=0, column=0)
        ttk.Label(bar, textvariable=self.time_var, style="Muted.TLabel").grid(row=0, column=1, padx=10)
        self._draw_placeholder()

    def _build_bottom(self) -> None:
        bottom = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom.grid(row=1, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        ttk.Label(bottom, text="Папка результата").grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(bottom, textvariable=self.out_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(bottom, text="Обзор…", command=self._browse_output).grid(row=0, column=2, padx=6)
        ttk.Button(bottom, text="Открыть", command=self.open_output_folder).grid(row=0, column=3)
        self.generate_btn = ttk.Button(bottom, text="GENERATE", style="Accent.TButton", command=self.generate)
        self.generate_btn.grid(row=0, column=4, padx=(14, 6))
        self.cancel_btn = ttk.Button(bottom, text="Отмена", command=self.cancel_export, state="disabled")
        self.cancel_btn.grid(row=0, column=5)
        self.progress = ttk.Progressbar(bottom, maximum=100, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(10, 2))
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").grid(row=2, column=0, columnspan=6, sticky="w")

    def _bind_keys(self) -> None:
        # по keycode, чтобы работало и на русской раскладке (O=79, G=71 в Windows)
        self.bind_all("<Control-Key>", self._on_ctrl_key)

    def _on_ctrl_key(self, event) -> None:
        if event.keycode == 79 or str(event.keysym).lower() == "o":
            self.import_audio()
        elif event.keycode == 71 or str(event.keysym).lower() == "g":
            self.generate()

    # ================= визуал =================
    def _collect_visual(self) -> VisualConfig:
        rev_bg = {v: k for k, v in BG_LABELS.items()}
        rev_font = {v[0]: k for k, v in FONTS.items()}
        data = {
            "title": self.title_var.get(), "subtitle": self.subtitle_var.get(), "title_caps": self.caps_var.get(),
            "use_template_palette": self.palette_var.get(), "bg_mode": rev_bg.get(self.bg_mode_var.get(), "gradient"),
            "bg_image": self.bg_image_var.get(), "bg_dim": self._num(self.bg_dim_var, 0.55),
            "font_key": rev_font.get(self.font_var.get(), "auto"), "font_path": self.font_path_var.get(),
            "title_scale": self._num(self.title_scale_var, 1.0), "sensitivity": self._num(self.sens_var, 1.0),
            "glow": self.glow_var.get(), "glow_strength": self._num(self.glow_strength_var, 0.7),
            "show_progress": self.progress_var.get(), "title_animation": self.anim_var.get(),
            **{k: var.get() for k, var in self.color_vars.items()},
        }
        return VisualConfig.from_dict(data)

    @staticmethod
    def _num(var: tk.DoubleVar, default: float) -> float:
        try:
            return float(var.get())
        except (tk.TclError, ValueError):
            return default

    def _apply_visual_to_vars(self, cfg: VisualConfig, keep_text: bool = True) -> None:
        self._building = True
        try:
            if not keep_text:
                self.title_var.set(cfg.title)
            self.subtitle_var.set(cfg.subtitle)
            self.caps_var.set(cfg.title_caps)
            self.palette_var.set(cfg.use_template_palette)
            for key, var in self.color_vars.items():
                var.set(getattr(cfg, key))
            self.bg_mode_var.set(BG_LABELS[cfg.bg_mode])
            self.bg_image_var.set(cfg.bg_image)
            self.bg_dim_var.set(cfg.bg_dim)
            self.font_var.set(FONTS[cfg.font_key][0])
            self.font_path_var.set(cfg.font_path)
            self.title_scale_var.set(cfg.title_scale)
            self.sens_var.set(cfg.sensitivity)
            self.glow_var.set(cfg.glow)
            self.glow_strength_var.set(cfg.glow_strength)
            self.progress_var.set(cfg.show_progress)
            self.anim_var.set(cfg.title_animation)
        finally:
            self._building = False
        self._on_visual_change()

    def _on_visual_change(self, *_args) -> None:
        if self._building:
            return
        self.session.visual = self._collect_visual()
        state = "disabled" if self.palette_var.get() else "normal"
        for btn in self._palette_buttons:
            btn.configure(state=state)
        self._schedule_preview()

    def _pick_color(self, key: str) -> None:
        _rgb, hex_value = colorchooser.askcolor(color=self.color_vars[key].get(), parent=self, title="Выбор цвета")
        if hex_value:
            self.color_vars[key].set(hex_value)
            if key != "text_color" and self.palette_var.get():
                self.palette_var.set(False)

    def _pick_bg_image(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Фоновое изображение", filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Все файлы", "*.*")])
        if path:
            self.bg_image_var.set(path)
            self.bg_mode_var.set(BG_LABELS["image"])

    def _pick_font(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Файл шрифта", filetypes=[("Шрифты", "*.ttf *.otf"), ("Все файлы", "*.*")])
        if path:
            self.font_path_var.set(path)
            self.font_var.set(FONTS["custom"][0])

    def save_preset(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Сохранить пресет", defaultextension=".json", initialdir=self.settings.last_preset_dir or None,
                                            filetypes=[("Пресет визуала", "*.json")])
        if not path:
            return
        data = self._collect_visual().to_dict()
        data.pop("title", None)
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Пресет", f"Не удалось сохранить: {exc}", parent=self)
            return
        self.settings.last_preset_dir = str(Path(path).parent)
        self._status(f"Пресет сохранён: {Path(path).name}")

    def load_preset(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Загрузить пресет", initialdir=self.settings.last_preset_dir or None, filetypes=[("Пресет визуала", "*.json")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Пресет", f"Не удалось прочитать пресет: {exc}", parent=self)
            return
        self.settings.last_preset_dir = str(Path(path).parent)
        self._apply_visual_to_vars(VisualConfig.from_dict(data), keep_text=True)
        self._status(f"Пресет загружен: {Path(path).name}")

    def reset_visual(self) -> None:
        self._apply_visual_to_vars(VisualConfig(), keep_text=True)
        self._status("Визуал сброшен к значениям по умолчанию.")

    # ================= шаблоны =================
    def _on_templates_change(self, *_args) -> None:
        if self._building:
            return
        chosen = [tid for tid, var in self.tpl_vars.items() if var.get()]
        if not chosen:
            first = self.session.templates[0] if self.session.templates else next(iter(TEMPLATES))
            self._building = True
            self.tpl_vars[first].set(True)
            self._building = False
            chosen = [first]
            self._status("Должен быть выбран хотя бы один шаблон.")
        self.session.templates = chosen
        names = [TEMPLATES[t].name for t in chosen]
        self.preview_combo.configure(values=names)
        if self.preview_tpl_var.get() not in names:
            self.preview_tpl_var.set(names[0])
        self._schedule_preview()

    def _preview_template_id(self) -> str:
        chosen = self.session.templates
        picked = self.preview_tpl_var.get()
        for tid in chosen:
            if picked == TEMPLATES[tid].name:
                return tid
        return chosen[0]

    def _on_preview_template_picked(self) -> None:
        self._schedule_preview()

    # ================= аудио и выбор фрагмента =================
    def import_audio(self) -> None:
        if self._busy():
            return
        path = filedialog.askopenfilename(parent=self, title="Импорт бита", initialdir=self.settings.last_import_dir or None, filetypes=AUDIO_TYPES)
        if path:
            self.load_audio(path)

    def load_audio(self, path: str) -> None:
        if self._loading or self._export_thread is not None:
            return
        self.stop_play()
        self._loading = True
        self._status(f"Загрузка: {Path(path).name} …")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

        def worker() -> None:
            try:
                self.session.load_audio(path)
                self._queue.put(("loaded", path))
            except Exception as exc:  # noqa: BLE001
                log.exception("Ошибка загрузки аудио")
                self._queue.put(("load_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _after_loaded(self, path: str) -> None:
        self._loading = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        audio = self.session.audio
        self.settings.last_import_dir = str(Path(path).parent)
        self.file_var.set(audio.name)
        note = "  ·  трек длиннее 20 минут обрезан" if audio.truncated else ""
        self.info_var.set(f"Длительность {format_time(audio.duration)}  ·  {audio.sample_rate} Гц, стерео{note}")
        self.wave.set_audio(self.session.peaks, audio.duration)
        self._preview_t = 0.0
        if not self.title_var.get().strip():
            self.title_var.set(Path(path).stem)
        self._sync_selection()
        self._status("Бит загружен. Выберите фрагмент, шаблоны и нажмите GENERATE.")

    def _on_wave_change(self, start: float, end: float) -> None:
        self.session.set_selection(start, end)
        self._sync_selection(update_wave=False)

    def _sync_selection(self, update_wave: bool = True) -> None:
        s = self.session
        self.start_var.set(format_time(s.start))
        self.end_var.set(format_time(s.end))
        self.length_var.set(f"Длина: {s.selection_length:.1f} с")
        if update_wave:
            self.wave.set_selection(s.start, s.end)
        self._preview_t = min(self._preview_t, max(0.0, s.selection_length - 0.05))
        self._update_scale_range()
        self._schedule_preview()

    def _apply_entries(self) -> None:
        if self.session.audio is None:
            return
        try:
            a, b = parse_time(self.start_var.get()), parse_time(self.end_var.get())
        except ValueError:
            self._status("Неверный формат времени. Пример: 1:23.5 или 83.5")
            self._sync_selection()
            return
        self.session.set_selection(a, b)
        self._sync_selection()

    def _set_length(self, seconds: float) -> None:
        if self.session.audio is None:
            return
        self.session.set_selection(self.session.start, self.session.start + seconds)
        self._sync_selection()

    def _auto_select(self) -> None:
        if self.session.audio is None:
            return
        length = self.session.selection_length or self.settings.default_length
        self.session.auto_select(length)
        self._sync_selection()
        self._status("Выбран самый энергичный фрагмент трека.")

    # ================= предпросмотр и воспроизведение =================
    def _draw_placeholder(self) -> None:
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(PREVIEW_W / 2, PREVIEW_H / 2, text="Импортируйте бит,\nчтобы увидеть предпросмотр", fill=theme.MUTED, justify="center", font=("Segoe UI", 11))

    def _update_scale_range(self) -> None:
        length = max(0.1, self.session.selection_length)
        self.scale.configure(to=length)
        self._set_scale(self._preview_t)

    def _set_scale(self, value: float) -> None:
        self._setting_scale = True
        try:
            self.scale.set(value)
        finally:
            self._setting_scale = False
        self.time_var.set(f"{self._fmt(value)} / {self._fmt(self.session.selection_length)}")

    @staticmethod
    def _fmt(seconds: float) -> str:
        m = int(seconds // 60)
        return f"{m}:{seconds - m * 60:04.1f}"

    def _on_scrub(self, value) -> None:
        if self._setting_scale:
            return
        if self._playing:
            self.stop_play()
        self._preview_t = float(value)
        self.time_var.set(f"{self._fmt(self._preview_t)} / {self._fmt(self.session.selection_length)}")
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
        self._preview_job = self.after(60, self._refresh_preview)

    def _refresh_preview(self) -> None:
        self._preview_job = None
        if self.session.audio is None:
            self._draw_placeholder()
            return
        try:
            image = self.session.render_preview(self._preview_template_id(), self._preview_t, PREVIEW_W)
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка предпросмотра")
            self._status(f"Ошибка предпросмотра: {exc}")
            return
        self._photo = ImageTk.PhotoImage(image)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def toggle_play(self) -> None:
        if self._playing:
            self.stop_play()
        else:
            self.start_play()

    def start_play(self) -> None:
        if self.session.audio is None:
            self._status("Сначала импортируйте бит.")
            return
        if self._busy():
            return
        length = self.session.selection_length
        offset = self._preview_t if self._preview_t < length - 0.3 else 0.0
        self._play_offset = offset
        if winsound is not None:
            try:
                path = self.session.write_preview_audio(offset)
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as exc:  # noqa: BLE001
                log.exception("Ошибка воспроизведения")
                self._status(f"Звук недоступен: {exc}")
        else:
            self._status("Звук предпросмотра доступен только в Windows; показывается картинка.")
        self._playing = True
        self._play_started = time.perf_counter()
        self.play_btn.configure(text="■ Стоп")
        self._tick()

    def stop_play(self) -> None:
        if not self._playing:
            return
        self._playing = False
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:  # noqa: BLE001
                pass
        self.play_btn.configure(text="▶ Играть")
        self.wave.set_playhead(None)

    def _tick(self) -> None:
        if not self._playing:
            return
        elapsed = self._play_offset + time.perf_counter() - self._play_started
        if elapsed >= self.session.selection_length:
            self.stop_play()
            self._preview_t = 0.0
            self._set_scale(0.0)
            self._refresh_preview()
            return
        self._preview_t = elapsed
        self._set_scale(elapsed)
        self.wave.set_playhead(elapsed)
        self._refresh_preview()
        self.after(30, self._tick)

    # ================= экспорт =================
    def _busy(self) -> bool:
        if self._export_thread is not None:
            self._status("Идёт экспорт. Дождитесь завершения или нажмите «Отмена».")
            return True
        return self._loading

    def generate(self) -> None:
        if self._busy():
            return
        audio = self.session.audio
        if audio is None:
            messagebox.showwarning("GENERATE", "Сначала импортируйте бит.", parent=self)
            return
        self.session.visual = self._collect_visual()
        job = self.session.build_job()
        errors = validate_job(job, audio.duration)
        if errors:
            messagebox.showerror("Нельзя начать генерацию", "\n".join(f"• {e}" for e in errors), parent=self)
            return
        self.stop_play()
        self._cancel.clear()
        self.generate_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.configure(mode="determinate", value=0)
        self._status("Подготовка…")

        def worker() -> None:
            try:
                paths = export_job(job, audio, progress=lambda p: self._queue.put(("progress", p)), cancel=self._cancel)
                self._queue.put(("done", paths))
            except ExportCancelled as exc:
                self._queue.put(("cancelled", exc.completed))
            except ValidationError as exc:
                self._queue.put(("error", "\n".join(exc.errors)))
            except ExportError as exc:
                self._queue.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001
                log.exception("Непредвиденная ошибка экспорта")
                self._queue.put(("error", f"Непредвиденная ошибка: {exc}"))

        self._export_thread = threading.Thread(target=worker, daemon=True)
        self._export_thread.start()

    def cancel_export(self) -> None:
        if self._export_thread is not None:
            self._cancel.set()
            self._status("Отмена…")

    def _poll_queue(self) -> None:
        latest = None
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "progress":
                    latest = payload
                else:
                    if latest is not None:  # сначала устаревший прогресс, затем итоговое событие
                        self._show_progress(latest)
                        latest = None
                    self._handle_event(kind, payload)
        except queue.Empty:
            pass
        if latest is not None:
            self._show_progress(latest)
        self.after(100, self._poll_queue)

    def _show_progress(self, p: ExportProgress) -> None:
        self.progress.configure(value=p.fraction * 100)
        if p.stage == "analyze":
            self._status("Анализ звука…")
        else:
            name = TEMPLATES[p.template_id].name
            self._status(f"Шаблон {p.job_index + 1}/{p.job_count}: {name} — кадр {p.frame}/{p.frame_count}")

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "loaded":
            self._after_loaded(payload)
        elif kind == "load_error":
            self._loading = False
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self._status("Не удалось загрузить файл.")
            messagebox.showerror("Импорт", payload, parent=self)
        elif kind in ("done", "cancelled", "error"):
            self._export_thread = None
            self.generate_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            if kind == "done":
                self.progress.configure(value=100)
                self._status(f"Готово: создано файлов — {len(payload)}.")
                listing = "\n".join(str(p) for p in payload)
                messagebox.showinfo("Готово", f"Готовые видео:\n\n{listing}", parent=self)
                if self.settings.open_folder_after:
                    self.open_output_folder()
            elif kind == "cancelled":
                self.progress.configure(value=0)
                self._status("Экспорт отменён." + (f" Уже готово файлов: {len(payload)}." if payload else ""))
            else:
                self.progress.configure(value=0)
                self._status("Ошибка экспорта.")
                messagebox.showerror("Ошибка экспорта", payload, parent=self)

    # ================= прочее =================
    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Папка для готовых видео", initialdir=self.out_var.get() or None)
        if folder:
            self.out_var.set(folder)

    def open_output_folder(self) -> None:
        folder = Path(self.out_var.get().strip() or self.settings.output_dir)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                self._status(f"Папка результата: {folder}")
        except OSError as exc:
            messagebox.showerror("Папка результата", f"Не удалось открыть папку: {exc}", parent=self)

    def open_settings(self) -> None:
        if self._busy():
            return
        SettingsDialog(self, self.settings, self._after_settings)

    def _after_settings(self) -> None:
        self.out_var.set(self.settings.output_dir)
        self._save_settings()
        self._status("Настройки сохранены.")

    def _status(self, text: str) -> None:
        self.status_var.set(text)

    def _show_keys(self) -> None:
        messagebox.showinfo("Горячие клавиши", "Ctrl+O — импорт бита\nCtrl+G — Generate\nПробел (в окне волны или предпросмотра) — слушать / стоп", parent=self)

    def _show_about(self) -> None:
        messagebox.showinfo("О программе", f"{APP_NAME} {__version__}\nЛокальная генерация вертикальных MP4 из битов.\nФайлы не покидают ваш компьютер.", parent=self)

    def _save_settings(self) -> None:
        try:
            self.settings.window_geometry = self.geometry()
            visual = self._collect_visual().to_dict()
            visual.pop("title", None)
            self.settings.visual = visual
            self.store.save(self.settings)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось сохранить настройки")

    def _on_close(self) -> None:
        if self._export_thread is not None:
            if not messagebox.askyesno("Выход", "Идёт экспорт. Отменить его и выйти?", parent=self):
                return
            self._cancel.set()
            self._export_thread.join(timeout=5)
        self.stop_play()
        self._save_settings()
        self.session.cleanup()
        self.destroy()

    def _report_exception(self, exc_type, exc, tb) -> None:
        log.error("Необработанное исключение в интерфейсе", exc_info=(exc_type, exc, tb))
        try:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {exc}\nПодробности в файле лога.", parent=self)
        except tk.TclError:
            pass
