from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
