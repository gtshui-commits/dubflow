from __future__ import annotations

from typing import Optional

from .base import ASRError, ASRProvider, BackendInfo, ProgressFn, Transcript


class WhisperCppProvider(ASRProvider):
    """Reserved for MVP2: whisper.cpp with Metal / CUDA / Vulkan backends
    (covers AMD GPUs on Windows/Linux). Not wired up yet."""

    name = "whisper.cpp"

    def __init__(self, backend: str = "vulkan") -> None:
        super().__init__(BackendInfo(
            name=self.name, device=backend,
            detail="whisper.cpp binary backend (planned)",
        ))

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        model_size: Optional[str] = None,
        progress: ProgressFn = None,
    ) -> Transcript:
        raise ASRError(
            "whisper.cpp backend is planned for MVP2 "
            "(target: AMD GPUs via Vulkan). Use mlx (mac) or faster-whisper for now."
        )
