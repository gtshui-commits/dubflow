from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict


class FFmpegError(RuntimeError):
    pass


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise FFmpegError(f"'{binary}' not found in PATH")
    return path


async def probe(video_path: str) -> Dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        _require("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {err.decode(errors='replace')[-800:]}")
    return json.loads(out.decode())


async def extract_audio(video_path: str, out_wav: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        _require("ffmpeg"), "-y", "-i", str(video_path), "-vn",
        "-ac", "1", "-ar", "16000", "-f", "wav", str(out_wav),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg extract failed: {err.decode(errors='replace')[-800:]}")


async def embed_subtitle(video_path: str, srt_path: str, out_path: str,
                         lang_code: str = "chi") -> None:
    """Soft-embed an SRT as a subtitle track (video/audio stream copy, no re-encode)."""
    out_ext = Path(out_path).suffix.lower()
    codec = "mov_text" if out_ext in (".mp4", ".m4v", ".mov") else "srt"
    proc = await asyncio.create_subprocess_exec(
        _require("ffmpeg"), "-y",
        "-i", str(video_path), "-i", str(srt_path),
        "-map", "0", "-map", "1:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", codec,
        "-metadata:s:s:0", f"language={lang_code}",
        str(out_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise FFmpegError(f"embed subtitle failed: {err.decode(errors='replace')[-800:]}")
