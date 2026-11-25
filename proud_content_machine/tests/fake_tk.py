"""Минимальная заглушка tkinter/ttk/PIL.ImageTk для проверки логики окна без дисплея.

Важно: это НЕ проверка настоящей отрисовки. Белый список методов защищает от опечаток в именах;
реальные методы tkinter, которых нет в списке, нужно добавлять вручную после сверки с документацией.
"""
import sys
import types

ALLOWED = {
    "grid", "pack", "columnconfigure", "rowconfigure", "bind", "bind_all", "focus_set", "winfo_width", "winfo_height",
    "delete", "create_line", "create_rectangle", "create_text", "create_image", "after_cancel", "title", "minsize",
    "geometry", "protocol", "mainloop", "destroy", "transient", "resizable", "grab_set", "add", "add_command",
    "add_cascade", "add_separator", "start", "stop", "option_add", "theme_use", "map", "lift",
}


class TclError(Exception):
    pass


class Var:
    def __init__(self, master=None, value=None, **_):
        self._v = value
        self._traces = []

    def get(self):
        return self._v

    def set(self, value):
        self._v = value
        for cb in list(self._traces):
            cb()

    def trace_add(self, _mode, cb):
        self._traces.append(lambda: cb("v", "", "write"))


class StringVar(Var):
    def __init__(self, master=None, value="", **kw):
        super().__init__(master, value)


class BooleanVar(Var):
    def __init__(self, master=None, value=False, **kw):
        super().__init__(master, bool(value))

    def set(self, value):
        super().set(bool(value))


class DoubleVar(Var):
    def __init__(self, master=None, value=0.0, **kw):
        super().__init__(master, float(value))


class Widget:
    after_queue = []

    def __init__(self, master=None, *args, **kw):
        self.master = master
        self.options = dict(kw)
        self._value = 0.0
        self._geometry = ""

    def __getattr__(self, name):
        if name in ALLOWED:
            return lambda *a, **k: None
        raise AttributeError(f"заглушка tkinter: неизвестный метод {name!r}")

    def configure(self, **kw):
        self.options.update(kw)

    config = configure

    def cget(self, key):
        return self.options.get(key)

    def winfo_width(self):
        return 600

    def winfo_height(self):
        return 150

    def set(self, value):
        self._value = value

    def get(self):
        return self._value

    def after(self, ms, fn=None, *args):
        Widget.after_queue.append(fn)
        return len(Widget.after_queue)

    def geometry(self, value=None):
        if value is not None:
            self._geometry = value
        return self._geometry or "1200x800+10+10"


class Tk(Widget):
    pass


class Toplevel(Widget):
    pass


class Canvas(Widget):
    pass


class Button(Widget):
    pass


class Menu(Widget):
    pass


class Style(Widget):
    def configure(self, *a, **k):
        return None

    def map(self, *a, **k):
        return None


class Calls:
    """Запись вызовов диалогов и заранее заданные ответы."""
    log = []
    answers = {}

    @classmethod
    def reset(cls):
        cls.log.clear()
        cls.answers.clear()


def _dialog(name, default):
    def fn(*args, **kwargs):
        Calls.log.append((name, args, kwargs))
        return Calls.answers.get(name, default)
    return fn


def install():
    tk = types.ModuleType("tkinter")
    tk.TclError = TclError
    for cls in (StringVar, BooleanVar, DoubleVar, Tk, Toplevel, Canvas, Button, Menu):
        setattr(tk, cls.__name__, cls)
    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Frame", "Label", "Entry", "Combobox", "Checkbutton", "Notebook", "Scale", "Progressbar", "LabelFrame", "Radiobutton"):
        setattr(ttk, name, type(name, (Widget,), {}))
    ttk.Button = type("Button", (Widget,), {})
    ttk.Style = Style
    mb = types.ModuleType("tkinter.messagebox")
    for name in ("showinfo", "showwarning", "showerror"):
        setattr(mb, name, _dialog(name, "ok"))
    mb.askyesno = _dialog("askyesno", True)
    fd = types.ModuleType("tkinter.filedialog")
    for name in ("askopenfilename", "asksaveasfilename", "askdirectory"):
        setattr(fd, name, _dialog(name, ""))
    cc = types.ModuleType("tkinter.colorchooser")
    cc.askcolor = _dialog("askcolor", (None, None))
    tk.ttk, tk.messagebox, tk.filedialog, tk.colorchooser = ttk, mb, fd, cc
    imagetk = types.ModuleType("PIL.ImageTk")
    imagetk.PhotoImage = lambda image=None, **kw: ("photo", getattr(image, "size", None))
    import PIL
    PIL.ImageTk = imagetk
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.messagebox": mb, "tkinter.filedialog": fd,
                        "tkinter.colorchooser": cc, "PIL.ImageTk": imagetk})
    return tk


def uninstall():
    for name in ("tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog", "tkinter.colorchooser", "PIL.ImageTk"):
        sys.modules.pop(name, None)
    for name in [m for m in sys.modules if m.startswith("pcm.gui")]:
        sys.modules.pop(name, None)
