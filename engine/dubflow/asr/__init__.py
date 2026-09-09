from __future__ import annotations

import logging
import platform
import sys
from typing import Optional

from .base import ASRProvider, ASRError

log = logging.getLogger(__name__)


def _mlx_available() -> bool:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    try:
        import mlx.core  # noqa: F401
        return True
    except Exception as e:  # pragma: no cover
        log.info("mlx unavailable: %s", e)
        return False


def _cuda_available() -> bool:
    try:
        import ctranslate2  # type: ignore
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def describe_backend() -> dict:
    """Report which backend would be selected without importing heavy models."""
    if _mlx_available():
        return {"name": "mlx-whisper", "device": "metal", "detail": "Apple Silicon GPU via MLX"}
    if _cuda_available():
        return {"name": "faster-whisper", "device": "cuda", "detail": "NVIDIA GPU via CTranslate2"}
    if _faster_whisper_available():
        return {"name": "faster-whisper", "device": "cpu", "detail": "CPU int8 fallback"}
    return {"name": "none", "device": "none", "detail": "no ASR backend installed"}


def select_provider(model_size: Optional[str] = None) -> ASRProvider:
    """Auto-select the fastest available backend for this machine."""
    if _mlx_available():
        from .mlx_provider import MLXWhisperProvider
        return MLXWhisperProvider()
    if _cuda_available():
        from .faster_provider import FasterWhisperProvider
        return FasterWhisperProvider(device="cuda", compute_type="float16")
    if _faster_whisper_available():
        from .faster_provider import FasterWhisperProvider
        return FasterWhisperProvider(device="cpu", compute_type="int8")
    raise ASRError(
        "No ASR backend available. Install mlx-whisper (macOS) or faster-whisper."
    )
