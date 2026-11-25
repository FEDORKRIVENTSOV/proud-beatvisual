import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    "README.md", "install.bat", "run.bat", "run_tests.bat", "requirements.txt",
    "pcm/__init__.py", "pcm/__main__.py", "pcm/audio.py", "pcm/config.py", "pcm/settings.py", "pcm/paths.py", "pcm/fonts.py",
    "pcm/ffmpeg_tools.py", "pcm/renderer.py", "pcm/exporter.py", "pcm/session.py", "pcm/templates/__init__.py",
    "pcm/templates/base.py", "pcm/templates/neon_wave.py", "pcm/templates/spectrum_bars.py", "pcm/templates/minimal_type.py",
    "pcm/gui/__init__.py", "pcm/gui/app.py", "pcm/gui/waveform.py", "pcm/gui/settings_dialog.py", "pcm/gui/theme.py",
]


class ProjectFilesTest(unittest.TestCase):
    def test_required_files_exist(self):
        missing = [f for f in REQUIRED if not (ROOT / f).is_file()]
        self.assertEqual(missing, [])

    def test_batch_files_are_crlf_without_bom(self):
        for name in ("install.bat", "run.bat", "run_tests.bat"):
            data = (ROOT / name).read_bytes()
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"), name)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), f"{name}: есть LF без CR")
            text = data.decode("utf-8")
            self.assertIn("chcp 65001", text)
            self.assertIn('cd /d "%~dp0"', text)

    def test_requirements_parse(self):
        lines = [l for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip()]
        names = {re.split(r"[<>=!~ ]", l)[0].lower() for l in lines}
        self.assertEqual(names, {"pillow", "numpy", "imageio-ffmpeg"})

    def test_no_todo_or_stub_markers(self):
        pattern = re.compile(r"\b(TODO|FIXME|NotImplementedError|pass\s*#\s*stub)\b")
        offenders = []
        for path in (ROOT / "pcm").rglob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and "base.py" not in path.name:
                    offenders.append(f"{path.name}:{n}")
        self.assertEqual(offenders, [])

    def test_core_modules_import(self):
        for mod in ("pcm", "pcm.audio", "pcm.config", "pcm.settings", "pcm.paths", "pcm.fonts", "pcm.ffmpeg_tools", "pcm.renderer",
                    "pcm.exporter", "pcm.session", "pcm.templates", "pcm.__main__"):
            importlib.import_module(mod)

    def test_all_sources_compile(self):
        for path in (ROOT / "pcm").rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
