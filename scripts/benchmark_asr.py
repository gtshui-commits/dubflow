#!/usr/bin/env python3
"""Benchmark available ASR backends on one audio file.

Usage:
  engine/.venv/bin/python scripts/benchmark_asr.py <audio_file> [--models tiny,base] [--repeats 2]

Compares mlx-whisper (Metal) and faster-whisper (CPU) with real timings
so you can decide whether a single whisper.cpp backend is enough.
"""
from __future__ import annotations

import argparse
import sys
import time
import wave
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

import mlx.core as mx  # noqa: E402

from dubflow.asr.base import BackendInfo  # noqa: E402
from dubflow.asr.mlx_provider import MLXWhisperProvider  # noqa: E402
from dubflow.asr.faster_provider import FasterWhisperProvider  # noqa: E402


class MLXCpuProvider(MLXWhisperProvider):
    """Same engine + same weights, but forced onto CPU. For GPU-vs-CPU comparison."""

    name = "mlx-cpu"

    def __init__(self) -> None:
        super().__init__()
        self.info = BackendInfo(self.name, "cpu", "MLX forced to CPU")

    def transcribe(self, *args, **kwargs):
        mx.set_default_device(mx.cpu)
        try:
            return super().transcribe(*args, **kwargs)
        finally:
            mx.set_default_device(mx.gpu)


def audio_duration(path: str) -> float:
    with closing(wave.open(path, "rb")) as wf:
        return wf.getnframes() / float(wf.getframerate() or 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--models", default="tiny,base")
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()

    dur = audio_duration(args.audio)
    print(f"audio: {args.audio} ({dur:.1f}s)\n")
    rows = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        for label, provider in [
            ("mlx/metal", MLXWhisperProvider()),
            ("mlx/cpu", MLXCpuProvider()),
            ("faster/cpu", FasterWhisperProvider("cpu", "int8")),
        ]:
            for r in range(args.repeats):
                t0 = time.perf_counter()
                try:
                    tr = provider.transcribe(args.audio, model_size=model)
                    dt = time.perf_counter() - t0
                    rows.append((model, label, r + 1, dt, len(tr.segments),
                                 tr.segments[0].text[:40] if tr.segments else ""))
                except Exception as e:
                    rows.append((model, label, r + 1, None, 0, f"UNAVAILABLE: {type(e).__name__}"))

    print(f"{'model':<16}{'backend':<12}{'run':<5}{'secs':<8}{'RTF':<8}segs  first text")
    for model, label, r, dt, n, text in rows:
        if dt is None:
            print(f"{model:<16}{label:<12}{r:<5}{'-':<8}{'-':<8}{n}     {text}")
        else:
            print(f"{model:<16}{label:<12}{r:<5}{dt:<8.2f}{dt / dur:<8.2f}{n}     {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
