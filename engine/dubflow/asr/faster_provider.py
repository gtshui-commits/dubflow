from __future__ import annotations

import threading
import wave
from contextlib import closing
from typing import Dict, Optional, Tuple

from .base import ASRError, ASRProvider, BackendInfo, ProgressFn, Segment, Transcript
from ..config import settings

DEFAULT_MODEL = "base"


class FasterWhisperProvider(ASRProvider):
    """CTranslate2 backend: fastest on NVIDIA CUDA; int8 CPU as universal fallback.

    TODO(platform-nvidia):
      - N 卡 (Windows/Linux) 走本后端的 CUDA fp16 路线，代码已实现，
        待在真实 NVIDIA 机器上验证（驱动/cuDNN 依赖打包 + 精度/速度基准）。
      - CPU int8 兜底已可工作（模型经 GUI 模型管理器下载到 models_dir/）。
    """

    name = "faster-whisper"

    def __init__(self, device: str = "cpu", compute_type: str = "int8") -> None:
        super().__init__(BackendInfo(
            name=self.name, device=device,
            detail=f"CTranslate2 ({compute_type})",
        ))
        self.device = device
        self.compute_type = compute_type
        self._models: Dict[Tuple[str, str], object] = {}
        self._lock = threading.Lock()

    def _load(self, model_size: str):
        key = (model_size, self.device)
        with self._lock:
            if key not in self._models:
                try:
                    from faster_whisper import WhisperModel  # type: ignore
                except ImportError as e:
                    raise ASRError(
                        "faster-whisper is not installed. Run: pip install faster-whisper"
                    ) from e
                # local dir (downloaded via the GUI model manager) wins over HF hub
                local = settings.models_dir / model_size
                target = str(local) if (local / "model.bin").is_file() else model_size
                self._models[key] = WhisperModel(
                    target, device=self.device, compute_type=self.compute_type,
                )
        return self._models[key]

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        model_size: Optional[str] = None,
        progress: ProgressFn = None,
    ) -> Transcript:
        size = model_size or DEFAULT_MODEL
        if progress:
            progress(0.05, f"loading model {size} ({self.device})")
        model = self._load(size)

        duration = None
        try:
            with closing(wave.open(audio_path, "rb")) as wf:
                duration = wf.getnframes() / float(wf.getframerate() or 1)
        except Exception:
            pass

        segments_iter, info = model.transcribe(
            str(audio_path), language=language, beam_size=5, vad_filter=True,
        )
        segments = []
        for i, seg in enumerate(segments_iter):
            segments.append(Segment(start=float(seg.start), end=float(seg.end),
                                    text=str(seg.text).strip()))
            if progress and duration:
                progress(min(seg.end / duration, 1.0), f"segment {i + 1}")
        if progress:
            progress(1.0, f"{len(segments)} segments")
        return Transcript(language=getattr(info, "language", None), segments=segments)
