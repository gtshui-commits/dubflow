from __future__ import annotations

import asyncio
import json
import shutil
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
