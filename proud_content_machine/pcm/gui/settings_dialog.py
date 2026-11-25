"""Диалог настроек приложения."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import FPS_CHOICES, QUALITY, QUALITY_LABELS, RESOLUTIONS
from ..paths import check_writable
from ..settings import AppSettings


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings: AppSettings, on_save) -> None:
        super().__init__(master)
        self.title("Настройки")
        self.transient(master)
        self.resizable(False, False)
        self.settings = settings
        self.on_save = on_save
        pad = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self, padding=14)
        frame.grid(sticky="nsew")

        self.out_var = tk.StringVar(value=settings.output_dir)
        self.res_var = tk.StringVar(value=settings.resolution)
        self.fps_var = tk.StringVar(value=str(settings.fps))
        self.q_var = tk.StringVar(value=QUALITY_LABELS[settings.quality])
        self.fin_var = tk.StringVar(value=f"{settings.fade_in:g}")
        self.fout_var = tk.StringVar(value=f"{settings.fade_out:g}")
        self.len_var = tk.StringVar(value=f"{settings.default_length:g}")
        self.open_var = tk.BooleanVar(value=settings.open_folder_after)

        ttk.Label(frame, text="Папка результата").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.out_var, width=48).grid(row=0, column=1, **pad)
        ttk.Button(frame, text="Обзор…", command=self._browse).grid(row=0, column=2, **pad)
        ttk.Label(frame, text="Разрешение").grid(row=1, column=0, sticky="w", **pad)
        ttk.Combobox(frame, textvariable=self.res_var, values=list(RESOLUTIONS), state="readonly", width=14).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Кадров в секунду").grid(row=2, column=0, sticky="w", **pad)
        ttk.Combobox(frame, textvariable=self.fps_var, values=[str(v) for v in FPS_CHOICES], state="readonly", width=14).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Качество").grid(row=3, column=0, sticky="w", **pad)
        ttk.Combobox(frame, textvariable=self.q_var, values=[QUALITY_LABELS[k] for k in QUALITY], state="readonly", width=24).grid(row=3, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Fade in, сек").grid(row=4, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.fin_var, width=8).grid(row=4, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Fade out, сек").grid(row=5, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.fout_var, width=8).grid(row=5, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Длина фрагмента по умолчанию, сек").grid(row=6, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.len_var, width=8).grid(row=6, column=1, sticky="w", **pad)
        ttk.Checkbutton(frame, text="Открывать папку после генерации", variable=self.open_var).grid(row=7, column=0, columnspan=3, sticky="w", **pad)
        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(buttons, text="Сохранить", style="Accent.TButton", command=self._save).pack(side="right")
        self.grab_set()

    def _browse(self) -> None:
        folder = filedialog.askdirectory(parent=self, initialdir=self.out_var.get() or None, title="Папка для готовых видео")
        if folder:
            self.out_var.set(folder)

    def _save(self) -> None:
        try:
            fade_in = float(self.fin_var.get().replace(",", "."))
            fade_out = float(self.fout_var.get().replace(",", "."))
            length = float(self.len_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Настройки", "Fade и длина фрагмента должны быть числами.", parent=self)
            return
        if not (0 <= fade_in <= 5 and 0 <= fade_out <= 5):
            messagebox.showerror("Настройки", "Fade должен быть от 0 до 5 секунд.", parent=self)
            return
        if not (1 <= length <= 180):
            messagebox.showerror("Настройки", "Длина фрагмента: от 1 до 180 секунд.", parent=self)
            return
        out = self.out_var.get().strip()
        problem = check_writable(out) if out else "Укажите папку результата."
        if problem:
            messagebox.showerror("Настройки", problem, parent=self)
            return
        reverse = {v: k for k, v in QUALITY_LABELS.items()}
        s = self.settings
        s.output_dir, s.resolution, s.fps = out, self.res_var.get(), int(self.fps_var.get())
        s.quality = reverse.get(self.q_var.get(), "balanced")
        s.fade_in, s.fade_out, s.default_length = fade_in, fade_out, length
        s.open_folder_after = bool(self.open_var.get())
        self.on_save()
        self.destroy()
