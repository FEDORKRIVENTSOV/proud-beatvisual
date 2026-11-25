"""Проверка логики окна на заглушке tkinter (без дисплея). Настоящую отрисовку проверяет только запуск на Windows."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from tests import fake_tk
from tests.helpers import make_test_audio, media_info

_tmp_data = tempfile.TemporaryDirectory()
os.environ["PCM_DATA_DIR"] = _tmp_data.name
fake_tk.install()
from pcm.gui import app as app_module  # noqa: E402
from pcm.gui.settings_dialog import SettingsDialog  # noqa: E402


def tearDownModule():
    fake_tk.uninstall()
    _tmp_data.cleanup()


class GuiLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "Папка с пробелами"
        cls.wav = make_test_audio(cls.root / "мой бит.wav", 8)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        fake_tk.Calls.reset()
        self.app = app_module.PCMApp()
        self.app.settings.output_dir = str(self.root / "Результат")
        self.app.settings.resolution = "720x1280"
        self.app.settings.quality = "draft"
        self.app.settings.open_folder_after = False
        self.app.out_var.set(self.app.settings.output_dir)

    def tearDown(self):
        self.app.session.cleanup()

    def pump(self, until, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            self.app._poll_queue()
            if until():
                return
            time.sleep(0.05)
        self.fail("таймаут ожидания")

    def load(self):
        self.app.load_audio(str(self.wav))
        self.pump(lambda: self.app.session.audio is not None and not self.app._loading)

    def shown(self, name):
        return [c for c in fake_tk.Calls.log if c[0] == name]

    def test_load_select_preview(self):
        self.load()
        a = self.app
        self.assertEqual(a.file_var.get(), "мой бит.wav")
        self.assertEqual(a.title_var.get(), "мой бит")  # название подставляется из имени файла
        self.assertAlmostEqual(a.session.selection_length, 8.0, delta=0.01)  # трек короче 30 с
        a.start_var.set("1:00.0")
        a.end_var.set("abc")
        a._apply_entries()
        self.assertIn("Неверный формат", a.status_var.get())
        a.start_var.set("2.5")
        a.end_var.set("6")
        a._apply_entries()
        self.assertAlmostEqual((a.session.start, a.session.end), (2.5, 6.0), delta=0.001)
        a._set_length(15)
        self.assertLessEqual(a.session.end, 8.0)
        a._auto_select()
        a._refresh_preview()
        self.assertEqual(a._photo, ("photo", (288, 512)))

    def test_template_selection_rules(self):
        a = self.app
        for tid, var in a.tpl_vars.items():
            var.set(False)
        self.assertEqual(len(a.session.templates), 1)  # хотя бы один шаблон всегда выбран
        self.assertIn("хотя бы один", a.status_var.get())
        for var in a.tpl_vars.values():
            var.set(True)
        self.assertEqual(a.session.templates, ["neon_wave", "spectrum_bars", "minimal_type"])
        a.preview_tpl_var.set("Spectrum Bars")
        self.assertEqual(a._preview_template_id(), "spectrum_bars")

    def test_visual_vars_flow_into_session(self):
        a = self.app
        a.title_var.set("Тест")
        a.glow_var.set(False)
        a.sens_var.set(99.0)  # вне диапазона: зажимается
        a.palette_var.set(False)
        a.color_vars["accent"].set("#112233")
        v = a.session.visual
        self.assertEqual((v.title, v.glow, v.sensitivity, v.accent, v.use_template_palette), ("Тест", False, 2.5, "#112233", False))
        self.assertEqual(a._palette_buttons[0].cget("state"), "normal")
        a.palette_var.set(True)
        self.assertEqual(a._palette_buttons[0].cget("state"), "disabled")

    def test_generate_validation_errors_block_start(self):
        a = self.app
        a.generate()
        self.assertEqual(len(self.shown("showwarning")), 1)  # нет бита
        self.load()
        a.title_var.set("   ")
        a.generate()
        self.assertEqual(len(self.shown("showerror")), 1)
        self.assertIn("название", self.shown("showerror")[0][1][1])
        self.assertIsNone(a._export_thread)

    def test_generate_end_to_end(self):
        self.load()
        a = self.app
        a.title_var.set("Привет: мир")
        a.session.set_selection(1, 3)
        a._sync_selection()
        a.tpl_vars["minimal_type"].set(True)
        a.generate()
        self.assertEqual(str(a.generate_btn.cget("state")), "disabled")
        a.generate()  # повторный запуск во время экспорта игнорируется
        self.pump(lambda: a._export_thread is None)
        shown = self.shown("showinfo")
        self.assertEqual(len(shown), 1, fake_tk.Calls.log)
        files = sorted((self.root / "Результат").glob("*.mp4"))
        self.assertEqual(len(files), 2)
        for f in files:
            info = media_info(f)
            self.assertEqual((info["vcodec"], info["size"]), ("h264", (720, 1280)))
        self.assertEqual(str(a.generate_btn.cget("state")), "normal")

    def test_cancel(self):
        self.load()
        a = self.app
        a.title_var.set("Отмена")
        a.session.set_selection(0, 6)
        a.settings.output_dir = str(self.root / "Отмена")
        a.generate()
        a.cancel_export()
        self.pump(lambda: a._export_thread is None)
        self.assertEqual(list((self.root / "Отмена").glob("*.mp4")), [])
        self.assertIn("отменён", a.status_var.get().lower())

    def test_playback_without_winsound(self):
        self.load()
        a = self.app
        a.start_play()
        self.assertTrue(a._playing)
        a._tick()
        a.stop_play()
        self.assertFalse(a._playing)

    def test_presets_roundtrip(self):
        a = self.app
        a.title_var.set("не должно попасть в пресет")
        a.glow_strength_var.set(0.2)
        a.subtitle_var.set("sub")
        path = str(self.root / "пресет.json")
        fake_tk.Calls.answers["asksaveasfilename"] = path
        a.save_preset()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertNotIn("title", data)
        a.reset_visual()
        self.assertEqual(a.subtitle_var.get(), "")
        fake_tk.Calls.answers["askopenfilename"] = path
        a.load_preset()
        self.assertEqual((a.subtitle_var.get(), round(a.session.visual.glow_strength, 2)), ("sub", 0.2))
        self.assertEqual(a.title_var.get(), "не должно попасть в пресет")  # название не затирается
        Path(path).write_text("{битый", encoding="utf-8")
        a.load_preset()
        self.assertEqual(len(self.shown("showerror")), 1)

    def test_settings_dialog_validation_and_save(self):
        a = self.app
        saved = []
        dlg = SettingsDialog(a, a.settings, lambda: saved.append(1))
        dlg.fin_var.set("abc")
        dlg._save()
        self.assertEqual(saved, [])
        self.assertEqual(len(self.shown("showerror")), 1)
        dlg.fin_var.set("0,5")
        dlg.fps_var.set("60")
        dlg.q_var.set("Высокое")
        dlg.out_var.set(str(self.root / "новая папка"))
        dlg._save()
        self.assertEqual(saved, [1])
        s = a.settings
        self.assertEqual((s.fade_in, s.fps, s.quality), (0.5, 60, "high"))
        self.assertTrue((self.root / "новая папка").is_dir())

    def test_close_saves_settings_without_title(self):
        self.load()
        a = self.app
        a.title_var.set("секрет")
        a._on_close()
        saved = json.loads(a.store.path.read_text(encoding="utf-8"))
        self.assertNotIn("title", saved["visual"])
        self.assertEqual(saved["last_import_dir"], str(self.wav.parent))


if __name__ == "__main__":
    unittest.main()
