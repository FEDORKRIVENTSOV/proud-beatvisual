"""Тёмная тема ttk."""
from __future__ import annotations

from tkinter import ttk

BG = "#14141c"
PANEL = "#1c1c27"
FIELD = "#252533"
FG = "#e9e9f2"
MUTED = "#9a9ab0"
ACCENT = "#00d1e0"
ACCENT_DARK = "#00a3b0"


def apply_theme(root) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI", 11, "bold"))
    style.configure("TLabelframe", background=BG, foreground=FG, bordercolor=FIELD)
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT)
    style.configure("TButton", background=FIELD, foreground=FG, padding=(10, 5), borderwidth=0)
    style.map("TButton", background=[("active", "#33334a"), ("disabled", PANEL)], foreground=[("disabled", MUTED)])
    style.configure("Accent.TButton", background=ACCENT_DARK, foreground="#001418", font=("Segoe UI", 11, "bold"), padding=(18, 8))
    style.map("Accent.TButton", background=[("active", ACCENT), ("disabled", PANEL)], foreground=[("disabled", MUTED)])
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TRadiobutton", background=BG, foreground=FG)
    style.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG)
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG, arrowcolor=FG)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6))
    style.map("TNotebook.Tab", background=[("selected", FIELD)], foreground=[("selected", ACCENT)])
    style.configure("TScale", background=BG, troughcolor=FIELD)
    style.configure("Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT, bordercolor=FIELD)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DARK)
