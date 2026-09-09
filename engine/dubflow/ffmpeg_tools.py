from __future__ import annotations

import asyncio
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict


class FFmpegError(RuntimeError):
    pass


def _require(binary: str) -> str:
    """Prefer project-bundled binaries (bin/), fall back to system PATH.

    Bundled naming: ffmpeg-darwin-arm64, ffmpeg-win32-x86_64.exe,
    ffmpeg-linux-x86_64, ... (see scripts/fetch_ffmpeg.sh)."""
    if binary in ("ffmpeg", "ffprobe"):
        plat = f"{sys.platform}-{platform.machine()}"
        ext = ".exe" if sys.platform == "win32" else ""
        candidate = Path(__file__).resolve().parents[2] / "bin" / f"{binary}-{plat}{ext}"
        if candidate.is_file():
            return str(candidate)
    path = shutil.which(binary)
    if not path:
        raise FFmpegError(f"'{binary}' not found in project bin/ or PATH")
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


def wav_duration(path) -> float:
    import wave
    from contextlib import closing
    with closing(wave.open(str(path), "rb")) as wf:
        return wf.getnframes() / float(wf.getframerate() or 1)


async def burn_subtitles(video_path: str, srt_path: str, out_path: str,
                         duration: float | None = None,
                         workdir: str | None = None,
                         progress=None) -> None:
    """Hard-burn subtitles into the video (re-encode with libx264 + libass).

    workdir: run ffmpeg from this dir so the SRT can be referenced by a plain
    filename, avoiding ffmpeg filter path-escaping issues.
    """
    srt_ref = Path(srt_path).name if workdir else str(srt_path)
    vf = f"subtitles={srt_ref}"
    args = [
        _require("ffmpeg"), "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-progress", "pipe:1", "-nostats",
        str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workdir) if workdir else None,
    )
    async def drain_stderr():
        return (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
    stderr_task = asyncio.create_task(drain_stderr())
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").strip()
        if line.startswith("out_time=") and duration:
            try:
                h, m, s = line.split("=", 1)[1].split(":")
                t = int(h) * 3600 + int(m) * 60 + float(s)
                if progress:
                    progress(min(t / duration, 1.0), f"burning {int(t)}/{int(duration)}s")
            except (ValueError, IndexError):
                pass
    await proc.wait()
    err = await stderr_task
    if proc.returncode != 0:
        raise FFmpegError(f"burn subtitles failed: {err[-800:]}")
