import json
import os
import tempfile
import unittest
from pathlib import Path

from pcm.config import JobConfig, VisualConfig, validate_job
from pcm.paths import check_writable, format_time, parse_time, sanitize_filename, unique_path
from pcm.settings import AppSettings, SettingsStore
from tests.helpers import make_test_audio


class PathsTest(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize_filename('Привет: мир?'), "Привет_ мир_")
        self.assertEqual(sanitize_filename("a/b\\c|d*e"), "a_b_c_d_e")
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("  ...  "), "untitled")
        self.assertEqual(sanitize_filename(""), "untitled")
        self.assertLessEqual(len(sanitize_filename("я" * 500)), 80)
        self.assertEqual(sanitize_filename("Мой бит   №1 "), "Мой бит №1")

    def test_unique_path_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "бит_x.mp4").write_bytes(b"1")
            (base / "бит_x (2).mp4").write_bytes(b"2")
            self.assertEqual(unique_path(base, "бит_x", ".mp4").name, "бит_x (3).mp4")
            self.assertEqual(unique_path(base, "new", ".mp4").name, "new.mp4")

    def test_time_roundtrip(self):
        self.assertEqual(format_time(83.5), "1:23.500")
        self.assertAlmostEqual(parse_time("1:23.5"), 83.5)
        self.assertAlmostEqual(parse_time("83,5"), 83.5)
        for bad in ("", "abc", "-5", "1:2:3:4"):
            with self.assertRaises(ValueError):
                parse_time(bad)

    def test_check_writable(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(check_writable(Path(d) / "новая папка" / "вложенная"))
            f = Path(d) / "file.txt"
            f.write_text("x")
            self.assertIsNotNone(check_writable(f / "sub"))


class SettingsTest(unittest.TestCase):
    def test_roundtrip_and_clamping(self):
        with tempfile.TemporaryDirectory() as d:
            store = SettingsStore(Path(d) / "s.json")
            s = AppSettings(output_dir=str(Path(d) / "Видео"), fps=60, quality="high")
            store.save(s)
            loaded = store.load()
            self.assertEqual((loaded.output_dir, loaded.fps, loaded.quality), (s.output_dir, 60, "high"))
            (Path(d) / "s.json").write_text(json.dumps({"fps": 999, "quality": "x", "fade_in": 99, "resolution": "1x1"}))
            bad = store.load()
            self.assertEqual((bad.fps, bad.quality, bad.fade_in, bad.resolution), (30, "balanced", 5.0, "1080x1920"))

    def test_corrupt_file_is_backed_up_not_lost(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            path.write_text("{ not json", encoding="utf-8")
            loaded = SettingsStore(path).load()
            self.assertEqual(loaded.fps, 30)
            backups = list(Path(d).glob("s.corrupt-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "{ not json")


class ConfigTest(unittest.TestCase):
    def test_visual_from_dict_sanitizes(self):
        v = VisualConfig.from_dict({"accent": "red", "bg_dim": 5, "sensitivity": "abc", "bg_mode": "??", "font_key": "zzz", "glow": 0})
        self.assertEqual(v.accent, VisualConfig().accent)
        self.assertEqual(v.bg_dim, 0.9)
        self.assertEqual(v.sensitivity, 1.0)
        self.assertEqual((v.bg_mode, v.font_key, v.glow), ("gradient", "auto", False))
        self.assertIsInstance(VisualConfig.from_dict(None), VisualConfig)

    def test_validate_job(self):
        with tempfile.TemporaryDirectory() as d:
            wav = make_test_audio(Path(d) / "бит.wav", 4)
            ok = JobConfig(audio_path=str(wav), start=0, end=3, templates=["neon_wave"], visual=VisualConfig(title="T"), output_dir=str(Path(d) / "out"))
            self.assertEqual(validate_job(ok, 4.0), [])
            cases = {
                "title": dict(visual=VisualConfig(title="  ")),
                "templates0": dict(templates=[]),
                "templates4": dict(templates=["neon_wave", "spectrum_bars", "minimal_type", "x"]),
                "short": dict(end=0.2),
                "long": dict(end=500),
                "oob": dict(end=9),
                "audio": dict(audio_path=str(Path(d) / "нет.wav")),
                "image": dict(visual=VisualConfig(title="T", bg_mode="image", bg_image="/нет.png")),
                "odd": dict(width=1081),
                "fps": dict(fps=17),
            }
            for name, patch in cases.items():
                job = JobConfig(**{**ok.__dict__, **patch})
                self.assertTrue(validate_job(job, 4.0), name)


if __name__ == "__main__":
    unittest.main()
