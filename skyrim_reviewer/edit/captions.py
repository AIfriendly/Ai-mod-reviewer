"""Caption / chapter helpers.

We generate a simple .srt subtitle (one cue per segment) and a YouTube chapter
list computed from the REAL audio durations, so timestamps are accurate.
"""
from __future__ import annotations

from pathlib import Path

from ..models import Script


def _ts(seconds: float, sep: str = ",") -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def segment_durations(script: Script, pause: float = 0.45) -> list[float]:
    """Per-segment on-screen duration = narration audio + a small tail pause."""
    out = []
    for seg in script.segments:
        out.append((seg.audio_seconds or seg.target_seconds or 3.0) + pause)
    return out


def write_srt(script: Script, durations: list[float], out_path: Path) -> None:
    lines, t = [], 0.0
    for i, (seg, dur) in enumerate(zip(script.segments, durations), 1):
        start, end = t, t + dur
        lines += [str(i), f"{_ts(start)} --> {_ts(end)}", seg.narration.strip(), ""]
        t = end
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _ass_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _chunks(words: list[str], max_words: int = 3, max_chars: int = 26) -> list[str]:
    """Group words into short caption lines (a few words each)."""
    out, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and (len(cand) > max_chars or len(cur.split()) >= max_words):
            out.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


def _hex_to_ass(color: str) -> str:
    c = (color or "#d4af37").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except Exception:
        r, g, b = 212, 175, 55
    return f"&H00{b:02X}{g:02X}{r:02X}"      # ASS is &HAABBGGRR


def build_ass(segments, durations, size, out_path: Path,
              accent: str = "#d4af37") -> Path:
    """Write an .ass subtitle with short, animated caption lines for each spoken
    segment, timed within the segment by word count. Big, bold, centered, with a
    heavy outline so it reads on any footage — burned in at render time."""
    W, H = size
    fontsize = max(36, round(H * 0.05))
    margin_v = round(H * 0.20)               # sit above the lower-third strip
    primary = "&H00FFFFFF"                    # white text
    accent_ass = _hex_to_ass(accent)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Cap,DejaVu Sans,{fontsize},{primary},&H00101010,&H64000000,1,1,4,1,2,80,80,{margin_v}
Style: CapHi,DejaVu Sans,{fontsize},{accent_ass},&H00101010,&H64000000,1,1,4,1,2,80,80,{margin_v}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events, t = [], 0.0
    for seg, dur in zip(segments, durations):
        words = (seg.narration or "").split()
        if not words or dur <= 0:
            t += dur
            continue
        lines = _chunks(words)
        total_w = sum(len(ln.split()) for ln in lines) or 1
        start = t
        for i, ln in enumerate(lines):
            frac = len(ln.split()) / total_w
            end = start + dur * frac
            txt = ln.replace("{", "(").replace("}", ")")
            # \fad gives a quick fade-in/out; emphasise the rank lead-in word.
            style = "CapHi" if (i == 0 and seg.kind == "mod") else "Cap"
            events.append(
                f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},{style},,0,0,0,,"
                f"{{\\fad(90,90)}}{txt}")
            start = end
        t += dur
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def youtube_chapters(script: Script, durations: list[float]) -> list[str]:
    """'0:00 Intro' style chapter list for the description."""
    out, t = [], 0.0
    for seg, dur in zip(script.segments, durations):
        m, s = int(t // 60), int(t % 60)
        out.append(f"{m}:{s:02d} {seg.title}")
        t += dur
    return out
