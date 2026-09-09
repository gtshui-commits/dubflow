from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: Optional[str]
    segments: List[Segment]

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "segments": [asdict(s) for s in self.segments],
        }


@dataclass
class BackendInfo:
    name: str
    device: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# progress callback: (0.0~1.0, detail_message)
ProgressFn = Optional[Callable[[float, str], None]]


class ASRError(RuntimeError):
    pass


class ASRProvider(ABC):
    """All engines (mlx / faster-whisper / whisper.cpp) implement this interface."""

    name: str = "base"

    def __init__(self, info: BackendInfo) -> None:
        self.info = info

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        model_size: Optional[str] = None,
        progress: ProgressFn = None,
    ) -> Transcript:
        ...
