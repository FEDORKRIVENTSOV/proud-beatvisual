"""Декодирование аудио через FFmpeg, пики для волны, поиск лучшего фрагмента, анализ спектра."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ffmpeg_tools import find_ffmpeg, subprocess_kwargs

SAMPLE_RATE = 44100
MAX_DURATION_SEC = 20 * 60
N_BANDS = 48
FFT_SIZE = 4096


class AudioDecodeError(RuntimeError):
    pass


@dataclass
class AudioData:
    path: str
    samples: np.ndarray  # int16, форма (n, 2)
    sample_rate: int = SAMPLE_RATE
    truncated: bool = False

    @property
    def duration(self) -> float:
        return len(self.samples) / float(self.sample_rate)

    @property
    def name(self) -> str:
        return Path(self.path).name

    def segment_int16(self, start: float, end: float) -> np.ndarray:
        a = max(0, int(round(start * self.sample_rate)))
        b = min(len(self.samples), int(round(end * self.sample_rate)))
        return self.samples[a:b]

    def mono_float(self, start: float, end: float) -> np.ndarray:
        seg = self.segment_int16(start, end).astype(np.float32)
        if seg.size == 0:
            return np.zeros(0, dtype=np.float32)
        return seg.mean(axis=1) / 32768.0


def _decode(ffmpeg: str, input_path: str, display_path: str) -> AudioData:
    cmd = [
        ffmpeg, "-v", "error", "-nostdin", "-i", input_path, "-vn", "-map", "0:a:0",
        "-t", str(MAX_DURATION_SEC), "-f", "s16le", "-ac", "2", "-ar", str(SAMPLE_RATE), "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, **subprocess_kwargs())
    except OSError as exc:
        raise AudioDecodeError(f"Не удалось запустить FFmpeg: {exc}") from exc
    raw = proc.stdout
    if proc.returncode != 0 or len(raw) < 4:
        tail = proc.stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise AudioDecodeError(f"Не удалось прочитать аудио «{Path(display_path).name}». {tail}")
    raw = raw[: len(raw) // 4 * 4]
    samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)
    truncated = len(samples) >= (MAX_DURATION_SEC - 1) * SAMPLE_RATE
    return AudioData(path=display_path, samples=samples, truncated=truncated)


def decode_audio(path: str | Path, ffmpeg_exe: str | None = None) -> AudioData:
    """Читает любой формат, который понимает FFmpeg. При сбое с не-ASCII путём повторяет через временную копию."""
    src = Path(path)
    if not src.is_file():
        raise AudioDecodeError(f"Файл не найден: {src}")
    ffmpeg = ffmpeg_exe or find_ffmpeg()
    try:
        return _decode(ffmpeg, str(src), str(src))
    except AudioDecodeError as first_error:
        if str(src).isascii():
            raise
        tmpdir = tempfile.mkdtemp(prefix="pcm_in_")
        try:
            suffix = src.suffix if src.suffix.isascii() else ".bin"
            tmp = Path(tmpdir) / f"input{suffix}"
            shutil.copyfile(src, tmp)
            return _decode(ffmpeg, str(tmp), str(src))
        except (AudioDecodeError, OSError):
            raise first_error
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def compute_peaks(audio: AudioData, columns: int) -> np.ndarray:
    """Массив (columns, 2) из min/max в диапазоне -1..1 для отрисовки волны."""
    columns = max(1, int(columns))
    n = len(audio.samples)
    per = n // columns
    if per < 1:
        out = np.zeros((columns, 2), dtype=np.float32)
        if n:
            out[:n, 0] = audio.samples[:, 0] / 32768.0
            out[:n, 1] = audio.samples[:, 0] / 32768.0
        return out
    block = audio.samples[: per * columns].reshape(columns, per, 2)
    mins = block.min(axis=(1, 2)).astype(np.float32) / 32768.0
    maxs = block.max(axis=(1, 2)).astype(np.float32) / 32768.0
    return np.stack([mins, maxs], axis=1)


def best_segment(audio: AudioData, length: float, hop_sec: float = 0.5) -> tuple[float, float]:
    """Находит самое энергичное окно заданной длины."""
    duration = audio.duration
    if length >= duration:
        return 0.0, duration
    hop = max(1, int(hop_sec * audio.sample_rate))
    n_hops = len(audio.samples) // hop
    if n_hops < 2:
        return 0.0, min(length, duration)
    energy = np.empty(n_hops, dtype=np.float64)
    chunk = 512
    for a in range(0, n_hops, chunk):
        b = min(n_hops, a + chunk)
        blk = audio.samples[a * hop : b * hop, 0].reshape(b - a, hop).astype(np.float32)
        energy[a:b] = (blk * blk).mean(axis=1)
    win = max(1, int(round(length / hop_sec)))
    win = min(win, n_hops)
    cums = np.concatenate([[0.0], np.cumsum(energy)])
    sums = cums[win:] - cums[:-win]
    idx = int(np.argmax(sums))
    start = idx * hop_sec
    return start, min(start + length, duration)


def fade_samples(samples: np.ndarray, sample_rate: int, fade_in: float, fade_out: float) -> np.ndarray:
    """Косинусные fade in/out. Возвращает новый int16-массив."""
    out = samples.astype(np.float32)
    n = len(out)
    fi = min(int(fade_in * sample_rate), n // 2)
    fo = min(int(fade_out * sample_rate), n // 2)
    if fi > 0:
        out[:fi] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi, dtype=np.float32)))[:, None]
    if fo > 0:
        out[n - fo :] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo, dtype=np.float32)))[:, None]
    return np.clip(np.rint(out), -32768, 32767).astype(np.int16)


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.ascontiguousarray(samples, dtype="<i2").tobytes())


@dataclass
class AudioFeatures:
    fps: int
    n_frames: int
    bands: np.ndarray   # (n_frames, N_BANDS) 0..1
    level: np.ndarray   # (n_frames,) 0..1
    bass: np.ndarray    # (n_frames,) 0..1
    mono: np.ndarray    # float32 сигнал фрагмента
    sample_rate: int
    wave_peak: float

    def wave_window(self, frame: int, n_points: int, window_sec: float = 0.03) -> np.ndarray:
        """Фрагмент формы волны вокруг кадра, приведённый к n_points и диапазону -1..1."""
        center = int(frame / self.fps * self.sample_rate)
        half = max(2, int(window_sec * self.sample_rate / 2))
        a, b = center - half, center + half
        seg = self.mono[max(0, a) : max(0, b)]
        if len(seg) < 2:
            return np.zeros(n_points, dtype=np.float32)
        if a < 0:
            seg = np.pad(seg, (-a, 0))
        if len(seg) < 2:
            return np.zeros(n_points, dtype=np.float32)
        xs = np.linspace(0, len(seg) - 1, n_points)
        out = np.interp(xs, np.arange(len(seg)), seg) / self.wave_peak
        return np.clip(out, -1.0, 1.0).astype(np.float32)


def _smooth(values: np.ndarray, fps: int, attack: float = 0.7, release: float = 0.25) -> np.ndarray:
    """Быстрая атака и медленный спад по кадрам (не зависит от fps)."""
    a = 1.0 - (1.0 - attack) ** (30.0 / fps)
    r = 1.0 - (1.0 - release) ** (30.0 / fps)
    out = np.empty_like(values)
    prev = np.zeros(values.shape[1:], dtype=values.dtype)
    for i in range(len(values)):
        cur = values[i]
        prev = np.where(cur > prev, prev + (cur - prev) * a, prev + (cur - prev) * r)
        out[i] = prev
    return out


def analyze_segment(mono: np.ndarray, sample_rate: int, fps: int, n_bands: int = N_BANDS) -> AudioFeatures:
    """Считает признаки для каждого кадра видео: полосы спектра, громкость, бас."""
    mono = np.asarray(mono, dtype=np.float32)
    duration = len(mono) / float(sample_rate)
    n_frames = max(1, int(np.ceil(duration * fps)))
    freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / sample_rate)
    edges = np.geomspace(40.0, min(16000.0, sample_rate / 2 * 0.95), n_bands + 1)
    lo = np.searchsorted(freqs, edges[:-1])
    hi = np.maximum(np.searchsorted(freqs, edges[1:]), lo + 1)
    centers = np.sqrt(edges[:-1] * edges[1:])
    tilt_db = 3.0 * np.log2(centers / 1000.0)
    window = np.hanning(FFT_SIZE).astype(np.float32)
    padded = np.pad(mono, (FFT_SIZE // 2, FFT_SIZE))
    centers_idx = np.rint(np.arange(n_frames) / fps * sample_rate).astype(np.int64)
    offsets = np.arange(FFT_SIZE)
    band_mag = np.empty((n_frames, n_bands), dtype=np.float32)
    rms = np.empty(n_frames, dtype=np.float32)
    half_rms = max(8, int(sample_rate / fps))
    for a in range(0, n_frames, 256):
        b = min(n_frames, a + 256)
        seg = padded[centers_idx[a:b, None] + offsets[None, :]] * window
        mag = np.abs(np.fft.rfft(seg, axis=1)) / (FFT_SIZE / 4.0)
        cs = np.concatenate([np.zeros((b - a, 1), dtype=np.float64), np.cumsum(mag, axis=1, dtype=np.float64)], axis=1)
        band_mag[a:b] = ((cs[:, hi] - cs[:, lo]) / (hi - lo)).astype(np.float32)
        for k in range(a, b):
            c = centers_idx[k]
            part = mono[max(0, c - half_rms) : c + half_rms]
            rms[k] = float(np.sqrt(np.mean(part * part))) if len(part) else 0.0
    db = 20.0 * np.log10(band_mag + 1e-9) + tilt_db[None, :]
    ref = max(float(np.percentile(db, 98)), -60.0)
    bands = np.clip((db - (ref - 55.0)) / 55.0, 0.0, 1.0).astype(np.float32)
    bands = _smooth(bands, fps)
    rms_ref = max(float(np.percentile(rms, 98)), 1e-4)
    level = _smooth(np.clip(rms / rms_ref, 0.0, 1.0)[:, None].astype(np.float32), fps)[:, 0]
    bass_raw = bands[:, : max(3, n_bands // 8)].mean(axis=1)
    bass = np.clip(bass_raw, 0.0, 1.0) ** 1.5
    peak = float(np.percentile(np.abs(mono), 99.5)) if len(mono) else 0.0
    return AudioFeatures(
        fps=fps, n_frames=n_frames, bands=bands, level=level.astype(np.float32),
        bass=bass.astype(np.float32), mono=mono, sample_rate=sample_rate, wave_peak=max(peak, 1e-3),
    )
