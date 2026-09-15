from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    host: str
    port: int
    data_dir: Path
    models_dir: Path
    hf_endpoint: str
    translate_base_url: str
    translate_api_key: str
    translate_model: str
    msft_translator_key: str
    msft_translator_region: str

    @classmethod
    def load(cls) -> "Settings":
        default_data = Path.home() / ".dubflow"
        return cls(
            host=_env("DUBFLOW_HOST", "127.0.0.1"),
            port=int(_env("DUBFLOW_PORT", "8741")),
            data_dir=Path(_env("DUBFLOW_DATA_DIR", str(default_data))).expanduser(),
            models_dir=Path(_env("DUBFLOW_MODELS_DIR", str(Path.home() / ".dubflow" / "models"))).expanduser(),
            hf_endpoint=_env("HF_ENDPOINT", "https://hf-mirror.com"),
            translate_base_url=_env("DUBFLOW_TRANSLATE_BASE_URL", "https://api.openai.com/v1"),
            translate_api_key=_env("DUBFLOW_TRANSLATE_API_KEY", ""),
            translate_model=_env("DUBFLOW_TRANSLATE_MODEL", "gpt-4o-mini"),
            msft_translator_key=_env("DUBFLOW_MSFT_TRANSLATOR_KEY", ""),
            msft_translator_region=_env("DUBFLOW_MSFT_TRANSLATOR_REGION", "global"),
        )


settings = Settings.load()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)

# Prefer project-bundled ffmpeg/ffprobe (bin/) everywhere in the engine process,
# including third-party libs that shell out to bare "ffmpeg" (e.g. mlx_whisper).
_BIN_DIR = Path(__file__).resolve().parents[2] / "bin"
os.environ["PATH"] = f"{_BIN_DIR}{os.pathsep}" + os.environ.get("PATH", "")
# huggingface_hub reads this at import time; keep CN-friendly default,
# override with HF_ENDPOINT=https://huggingface.co if you prefer.
os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)


# ---------------------------------------------------------------------------
# 本地模型目录解析
#
# 下载器（downloads.CATALOG）落盘用的是它自己的键名，例如 "faster-whisper-base"；
# 而引擎在识别时收到的是 GUI 传来的别名，例如 "base"。两者对不上会导致
# 「模型明明下载好了，引擎却当本地不存在，转而去 HF 重下一遍」。
# 这里统一解析，三种命名都认：别名 / 下载器键名 / 带前缀的仓库短名。
# ---------------------------------------------------------------------------
_MODEL_DIR_ALIASES: Dict[str, str] = {
    "tiny": "faster-whisper-tiny",
    "base": "faster-whisper-base",
    "small": "faster-whisper-small",
    "medium": "faster-whisper-medium",
    "large-v3": "faster-whisper-large-v3",
    "large-v3-turbo": "faster-whisper-large-v3-turbo",
    "turbo": "faster-whisper-large-v3-turbo",
}


def resolve_model_dir(model_size: str) -> Optional[Path]:
    """返回本地已就绪的模型目录（要求内含 model.bin），没有则返回 None。"""
    names = [model_size]
    alias = _MODEL_DIR_ALIASES.get(model_size)
    if alias:
        names.append(alias)
    names.append(f"faster-whisper-{model_size}")
    for name in dict.fromkeys(names):
        candidate = settings.models_dir / name
        if (candidate / "model.bin").is_file():
            return candidate
    return None
