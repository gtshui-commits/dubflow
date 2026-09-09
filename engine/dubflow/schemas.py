from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel


class ASROptions(BaseModel):
    provider: str = "auto"          # auto | mlx-whisper | faster-whisper | whisper.cpp
    model: Optional[str] = None     # e.g. "large-v3-turbo" or any HF repo id


class TranslationOptions(BaseModel):
    enabled: bool = False
    provider: str = "llm"           # llm | google | microsoft
    base_url: Optional[str] = None  # llm only; default from settings (env)
    api_key: Optional[str] = None   # llm or microsoft(azure key)
    region: Optional[str] = None    # microsoft azure region, e.g. global
    model: Optional[str] = None     # llm only


class JobCreate(BaseModel):
    video_path: str
    source_language: Optional[str] = None   # None = auto detect
    target_language: str = "zh"
    asr: ASROptions = ASROptions()
    translation: TranslationOptions = TranslationOptions()
