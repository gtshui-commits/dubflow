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


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def describe_backend() -> dict:
    """Report which backend would be selected without importing heavy models."""
    if _is_apple_silicon():
        if _mlx_available():
            return {"name": "mlx-whisper", "device": "metal", "detail": "Apple Silicon GPU via MLX"}
        return {"name": "none", "device": "none",
                "detail": "macOS requires Metal GPU backend (pip install mlx-whisper)"}
    if _cuda_available():
        return {"name": "faster-whisper", "device": "cuda", "detail": "NVIDIA GPU via CTranslate2"}
    if _faster_whisper_available():
        return {"name": "faster-whisper", "device": "cpu", "detail": "CPU int8 fallback (non-mac)"}
    return {"name": "none", "device": "none", "detail": "no ASR backend installed"}


# ---------------------------------------------------------------------------
# TODO(backend-roadmap) 三平台显卡 -> Whisper 后端映射（自动探测 + 用户可覆盖）
#   [x] MacBook / Apple Silicon    : mlx-whisper (Metal GPU)  -> mlx_provider.py    已实现
#   [ ] NVIDIA (Windows/Linux)     : faster-whisper (CUDA fp16) -> faster_provider.py 代码就绪, TODO: 真机验证+cuDNN打包
#   [ ] AMD / Intel (Windows/Linux): whisper.cpp (Vulkan)      -> cpp_provider.py    TODO: MVP2 实现
#   [x] 兜底 (Windows/Linux 无 N 卡): faster-whisper CPU int8
# ---------------------------------------------------------------------------


def select_provider(model_size: Optional[str] = None) -> ASRProvider:
    """Auto-select the fastest available backend for this machine.

    Policy: macOS (Apple Silicon) is Metal-GPU-only - every Mac has Metal, so
    there is deliberately NO CPU fallback there. Windows/Linux use CUDA when an
    NVIDIA GPU is present, CPU int8 otherwise (Vulkan/whisper.cpp planned)."""
    if _is_apple_silicon():
        if _mlx_available():
            from .mlx_provider import MLXWhisperProvider
            return MLXWhisperProvider()
        raise ASRError(
            "macOS requires the Metal GPU backend (mlx-whisper) but it is not available. "
            "Install it with: pip install mlx-whisper"
        )
    if _cuda_available():
        from .faster_provider import FasterWhisperProvider
        return FasterWhisperProvider(device="cuda", compute_type="float16")
    if _faster_whisper_available():
        from .faster_provider import FasterWhisperProvider
        return FasterWhisperProvider(device="cpu", compute_type="int8")
    raise ASRError(
        "No ASR backend available. Install mlx-whisper (macOS) or faster-whisper (Windows/Linux)."
    )
