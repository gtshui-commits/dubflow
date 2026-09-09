from __future__ import annotations

from typing import Optional

from .base import ASRError, ASRProvider, BackendInfo, ProgressFn, Transcript


class WhisperCppProvider(ASRProvider):
    """A卡 (AMD) / Intel 显卡方案：whisper.cpp Vulkan 后端。

    TODO(MVP2) 三平台后端路线：
      - MacBook (M 系列):   mlx-whisper (Metal)         -> mlx_provider.py    [已实现]
      - NVIDIA (Win/Linux):  faster-whisper (CUDA fp16) -> faster_provider.py [代码就绪, 待真机验证]
      - AMD/Intel (Win/Linux): whisper.cpp (Vulkan)      -> cpp_provider.py    [本文件, 待实现]

    实现要点：
      1) 按平台捆绑 whisper.cpp 预编译二进制（Vulkan 版），或源码编译
      2) 通过 pywhispercpp / 子进程调用，输出归一化为 Transcript
      3) select_provider() 中检测 Vulkan 可用性后启用本 Provider
    """

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
