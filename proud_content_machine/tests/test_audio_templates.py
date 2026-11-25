import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import ImageChops

from pcm.audio import AudioData, AudioDecodeError, analyze_segment, best_segment, compute_peaks, decode_audio, fade_samples
from pcm.config import VisualConfig
from pcm.templates import TEMPLATES
from tests.helpers import make_test_audio

SR = 44100


class AudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.wav = make_test_audio(Path(cls.tmp.name) / "Папка с пробелами" / "Мой бит (демо).wav", 6)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_decode_cyrillic_path(self):
        a = decode_audio(self.wav)
        self.assertAlmostEqual(a.duration, 6.0, delta=0.05)
        self.assertEqual(a.samples.shape[1], 2)
        self.assertEqual(a.name, "Мой бит (демо).wav")

    def test_decode_errors(self):
        with self.assertRaises(AudioDecodeError):
            decode_audio(Path(self.tmp.name) / "нет.mp3")
        junk = Path(self.tmp.name) / "мусор.mp3"
        junk.write_bytes(b"not audio" * 100)
        with self.assertRaises(AudioDecodeError):
            decode_audio(junk)

    def test_peaks_and_best_segment(self):
        a = decode_audio(self.wav)
        p = compute_peaks(a, 300)
        self.assertEqual(p.shape, (300, 2))
        self.assertTrue((p[:, 0] <= p[:, 1]).all())
        # тихое начало, громкий конец
        quiet = np.zeros((SR * 10, 2), dtype=np.int16)
        quiet[SR * 7 :] = 20000
        b = AudioData("x", quiet)
        s, e = best_segment(b, 2.0)
        self.assertGreaterEqual(s, 6.5)
        self.assertEqual(best_segment(b, 99.0), (0.0, 10.0))

    def test_fade(self):
        x = np.full((SR, 2), 10000, dtype=np.int16)
        y = fade_samples(x, SR, 0.2, 0.2)
        self.assertEqual(y[0, 0], 0)
        self.assertEqual(y[-1, 0], 0)
        self.assertEqual(y[SR // 2, 0], 10000)

    def test_features_react_to_sound(self):
        t = np.arange(SR * 2) / SR
        sig = np.concatenate([np.zeros(SR), 0.6 * np.sin(2 * np.pi * 440 * t[:SR])]).astype(np.float32)
        f = analyze_segment(sig, SR, 30)
        self.assertEqual(f.bands.shape, (60, 48))
        self.assertLess(f.level[:25].max(), 0.05)
        self.assertGreater(f.level[40:].mean(), 0.5)
        self.assertGreater(f.bands[40:].max(), 0.7)
        self.assertEqual(float(f.bands[:25].max()), 0.0)  # цифровая тишина остаётся тишиной
        self.assertTrue(np.isfinite(f.bands).all())
        self.assertEqual(f.wave_window(45, 100).shape, (100,))
        empty = analyze_segment(np.zeros(0, dtype=np.float32), SR, 30)
        self.assertEqual(empty.n_frames, 1)


class TemplatesTest(unittest.TestCase):
    def setUp(self):
        t = np.arange(SR * 2) / SR
        self.loud = analyze_segment((0.7 * np.sin(2 * np.pi * 200 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32), SR, 20)
        self.silent = analyze_segment(np.zeros(SR * 2, dtype=np.float32), SR, 20)

    def test_every_template_renders_and_reacts(self):
        cfg = VisualConfig(title="Привет, мир", subtitle="prod. by X")
        for tid, cls in TEMPLATES.items():
            with self.subTest(template=tid):
                loud = cls(270, 480, cfg, self.loud)
                quiet = cls(270, 480, cfg, self.silent)
                a, b = loud.render(10), quiet.render(10)
                self.assertEqual(a.size, (270, 480))
                self.assertEqual(a.mode, "RGB")
                self.assertIsNotNone(ImageChops.difference(a, b).getbbox(), "звук не влияет на кадр")
                self.assertIsNotNone(a.getbbox())
                loud.render(10**6)  # индекс за пределами не падает
                loud.render(-5)

    def test_options_do_not_crash(self):
        import itertools

        for tid, cls in TEMPLATES.items():
            for glow, prog, anim, caps, palette in itertools.product((True, False), repeat=5):
                cfg = VisualConfig(title="Очень длинное название трека которое не помещается в одну строку никак" * 2, subtitle="", glow=glow,
                                   show_progress=prog, title_animation=anim, title_caps=caps, use_template_palette=palette, sensitivity=2.5)
                cls(180, 320, cfg, self.loud).render(3)
        for bg in ("solid", "image"):  # image без файла: запасной фон
            cls = TEMPLATES["neon_wave"]
            cls(180, 320, VisualConfig(title="x", bg_mode=bg, use_template_palette=False), self.loud).render(0)

    def test_background_image_and_text_fits(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "фон картинка.png"
            Image.new("RGB", (500, 300), (200, 30, 30)).save(img)
            cfg = VisualConfig(title="Т" * 200, bg_mode="image", bg_image=str(img), bg_dim=0.5)
            tpl = TEMPLATES["minimal_type"](360, 640, cfg, self.loud)
            self.assertLessEqual(tpl.title.w, 360)
            frame = tpl.render(0)
            self.assertGreater(frame.getpixel((5, 5))[0], 40)  # красный фон просвечивает


if __name__ == "__main__":
    unittest.main()
