from __future__ import annotations

from typing import List, Optional

from .asr.base import Segment


def _fmt_ts(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(segments: List[Segment], second_lines: Optional[List[str]] = None) -> str:
    """Render segments as SRT. Optionally add a translated second line per cue."""
    blocks = []
    for i, seg in enumerate(segments):
        lines = [str(i + 1), f"{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}"]
        lines.append(seg.text if not second_lines else f"{seg.text}\n{second_lines[i]}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
