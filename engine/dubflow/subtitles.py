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


def _fmt_ass(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    h, rem = divmod(total_cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def to_ass(segments: List[Segment], second_lines: Optional[List[str]] = None,
           font: str = "PingFang SC") -> str:
    """ASS with an explicit CJK-capable style; libass scales PlayRes to the video."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 384
PlayResY: 288
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{font},20,&H00FFFFFF,&H00000000,&H7F000000,0,1,0,2,15,15,25

[Events]
Format: Layer, Start, End, Style, Text
""".format(font=font)
    lines = [header]
    for i, seg in enumerate(segments):
        text = seg.text if not second_lines else f"{seg.text}\\N{second_lines[i]}"
        text = text.replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{_fmt_ass(seg.start)},{_fmt_ass(seg.end)},Default,{text}")
    return "\n".join(lines) + "\n"
