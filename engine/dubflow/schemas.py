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


class ExportOptions(BaseModel):
    variant: str = "bilingual"      # source | target | bilingual  (三选一)
    save_to_video_folder: bool = True   # 交付方式一：字幕存到原视频所在文件夹
    embed_video: bool = False           # 交付方式二：同时嵌入字幕生成新视频


class JobCreate(BaseModel):
    video_path: str
    source_language: Optional[str] = None   # None = auto detect
    target_language: str = "zh"
    asr: ASROptions = ASROptions()
    translation: TranslationOptions = TranslationOptions()
    export: ExportOptions = ExportOptions()
