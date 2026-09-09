from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel


class ASROptions(BaseModel):
    provider: str = "auto"          # auto | mlx-whisper | faster-whisper | whisper.cpp
    model: Optional[str] = None     # e.g. "large-v3-turbo" or any HF repo id


class TranslationOptions(BaseModel):
    enabled: bool = False
    base_url: Optional[str] = None  # default from settings (env)
    api_key: Optional[str] = None
    model: Optional[str] = None


class JobCreate(BaseModel):
    video_path: str
    source_language: Optional[str] = None   # None = auto detect
    target_language: str = "zh"
    asr: ASROptions = ASROptions()
    translation: TranslationOptions = TranslationOptions()
