import tempfile
import threading
import unittest
from pathlib import Path

from pcm.audio import decode_audio
from pcm.config import JobConfig, VisualConfig
from pcm.exporter import ExportCancelled, ValidationError, export_job
from pcm.session import Session
from pcm.settings import AppSettings
from tests.helpers import make_test_audio, media_info


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "Папка с пробелами и кириллицей"
        cls.wav = make_test_audio(cls.root / "Бит №1 (демо).wav", 6)
        cls.audio = decode_audio(cls.wav)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def job(self, **kw):
        base = dict(audio_path=self.audio.path, start=1.0, end=3.5, templates=["neon_wave", "spectrum_bars", "minimal_type"],
                    visual=VisualConfig(title="Привет: мир?", subtitle="prod. by тест"), output_dir=str(self.root / "Готовые видео"),
                    width=360, height=640, fps=30, quality="draft")
        base.update(kw)
        return JobConfig(**base)

    def test_three_templates_produce_valid_vertical_mp4(self):
        progress = []
        out = export_job(self.job(output_dir=str(self.root / "out1")), self.audio, progress=progress.append)
        self.assertEqual(len(out), 3)
        self.assertTrue(all(p.parent.name == "out1" and p.suffix == ".mp4" for p in out))
        self.assertTrue(out[0].name.endswith("_neon_wave.mp4"), out[0].name)
        self.assertTrue(out[0].name.startswith("Привет_ мир_"), out[0].name)
        for p in out:
            info = media_info(p)
            self.assertEqual(info["vcodec"], "h264")
            self.assertEqual(info["acodec"], "aac")
            self.assertEqual(info["size"], (360, 640))
            self.assertAlmostEqual(info["duration"], 2.5, delta=0.15)
        self.assertAlmostEqual(progress[-1].fraction, 1.0, places=3)
        self.assertEqual(sorted(p.template_id for p in progress if p.stage == "render")[0], "minimal_type")

    def test_default_full_hd_size(self):
        out = export_job(self.job(output_dir=str(self.root / "hd"), templates=["spectrum_bars"], start=0, end=1.0, width=1080, height=1920, fps=24), self.audio)
        self.assertEqual(media_info(out[0])["size"], (1080, 1920))

    def test_existing_files_are_not_overwritten(self):
        d = self.root / "out2"
        job = self.job(output_dir=str(d), templates=["neon_wave"], end=2.0)
        first = export_job(job, self.audio)[0]
        marker = first.stat().st_mtime_ns
        second = export_job(job, self.audio)[0]
        self.assertNotEqual(first, second)
        self.assertIn("(2)", second.name)
        self.assertEqual(first.stat().st_mtime_ns, marker)

    def test_invalid_job_raises_and_writes_nothing(self):
        d = self.root / "out3"
        with self.assertRaises(ValidationError) as ctx:
            export_job(self.job(output_dir=str(d), visual=VisualConfig(title="")), self.audio)
        self.assertTrue(any("название" in e for e in ctx.exception.errors))
        self.assertEqual(list(d.glob("*.mp4")) if d.exists() else [], [])

    def test_cancel_cleans_temp_and_outputs(self):
        d = self.root / "out4"
        cancel = threading.Event()

        def on_progress(p):
            if p.frame >= 5:
                cancel.set()

        with self.assertRaises(ExportCancelled) as ctx:
            export_job(self.job(output_dir=str(d)), self.audio, progress=on_progress, cancel=cancel)
        self.assertEqual(ctx.exception.completed, [])
        self.assertEqual(list(d.glob("*.mp4")), [])


class SessionTest(unittest.TestCase):
    def test_selection_and_preview(self):
        with tempfile.TemporaryDirectory() as d:
            wav = make_test_audio(Path(d) / "бит.wav", 8)
            s = Session(AppSettings(output_dir=str(Path(d) / "out"), default_length=4))
            try:
                s.load_audio(wav)
                self.assertAlmostEqual(s.selection_length, 4.0, delta=0.01)
                self.assertEqual(s.set_selection(-5, 100), (0.0, 8.0))
                a, b = s.set_selection(7.5, 7.6)
                self.assertGreaterEqual(b - a, 1.0)
                self.assertLessEqual(b, 8.0)
                self.assertEqual(s.set_selection(5, 2), s.set_selection(2, 5))
                s.set_selection(1, 4)
                img = s.render_preview("spectrum_bars", 1.0, 270)
                self.assertEqual(img.size, (270, 480))
                self.assertTrue(s.write_preview_audio(1.5).is_file())
                job = s.build_job()
                self.assertEqual((job.width, job.height), (1080, 1920))
                s.settings.resolution = "720x1280"
                self.assertEqual((s.build_job().width, s.build_job().height), (720, 1280))
            finally:
                s.cleanup()


if __name__ == "__main__":
    unittest.main()
