"""Точка входа: python -m pcm [путь_к_биту]"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import app_data_dir


def setup_logging() -> Path:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pcm.log"
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    sys.excepthook = lambda t, e, tb: logging.getLogger("pcm").error("Необработанное исключение", exc_info=(t, e, tb))
    return log_path


def _enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    log_path = setup_logging()
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Не найден tkinter. Переустановите Python с python.org и отметьте компонент 'tcl/tk and IDLE'.")
        return 1
    _enable_dpi_awareness()
    from .gui.app import PCMApp

    initial = args[0] if args and Path(args[0]).is_file() else None
    try:
        app = PCMApp(initial_audio=initial)
        app.mainloop()
    except Exception:  # noqa: BLE001
        logging.getLogger("pcm").exception("Критическая ошибка запуска")
        print(f"Критическая ошибка. Подробности: {log_path}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
