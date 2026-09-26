"""Caption / chapter helpers.

We generate a simple .srt subtitle (one cue per segment) and a YouTube chapter
list computed from the REAL audio durations, so timestamps are accurate.
"""
from __future__ import annotations

import re
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


def write_srt(script: Script, durations: list[float], out_path: Path,
              extra_gaps: dict | None = None, start_offset: float = 0.0) -> None:
    extra_gaps = extra_gaps or {}
    lines, t = [], float(start_offset)
    for i, (seg, dur) in enumerate(zip(script.segments, durations), 1):
        start, end = t, t + dur
        lines += [str(i), f"{_ts(start)} --> {_ts(end)}", seg.narration.strip(), ""]
        t = end + extra_gaps.get(seg.segment_id, 0.0)
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
              accent: str = "#d4af37", start_offset: float = 0.0,
              extra_gaps: dict | None = None) -> Path:
    """Write an .ass subtitle with short, animated caption lines for each spoken
    segment, timed within the segment by word count. Big, bold, centered, with a
    heavy outline so it reads on any footage — burned in at render time.

    `start_offset` shifts all timings later (seconds) — used when a cold-open teaser
    is prepended to the video so captions still line up with the narration.
    `extra_gaps` (segment_id -> seconds) accounts for non-narrated clips spliced in
    right after a segment (e.g. ranked_tier_list's verdict card), so later segments'
    captions still line up with their real position in the concatenated video."""
    W, H = size
    fontsize = max(36, round(H * 0.05))
    # Clear the lower-third AND its "FREE ON NEXUS" pill, whose top edge is exactly
    # H*0.20 at 1080p — at that margin descenders and the outline ran into it.
    margin_v = round(H * 0.222)
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
    extra_gaps = extra_gaps or {}
    events, t = [], float(start_offset)
    for seg, dur in zip(segments, durations):
        gap = extra_gaps.get(seg.segment_id, 0.0)
        words = (seg.narration or "").split()
        if not words or dur <= 0:
            t += dur + gap
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
        t += dur + gap
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def _clean_chapter_name(name: str) -> str:
    """Tidy raw Nexus mod names for chapter labels (drop edition tags / dangling dashes)."""
    import re
    n = re.sub(r"\s*[-–]\s*(SSE|SE|AE|LE|Special Edition|MOD)\b.*$", "", name or "",
               flags=re.I)
    n = re.sub(r"\s*\((SSE|SE|AE|LE)\)\s*$", "", n, flags=re.I)
    n = re.sub(r"\bMOD\b\s*[-–]?\s*$", "", n, flags=re.I)
    return n.strip(" -–") or (name or "").strip()


# Separator between a chapter's label and its mod link. Distinctive enough that the
# description builder can split it back off without touching mod names.
CHAPTER_LINK_SEP = " — "


def youtube_chapters(script: Script, durations: list[float],
                     mods=None, start_offset: float = 0.0,
                     extra_gaps: dict | None = None,
                     link_mods: bool = False) -> list[str]:
    """'0:00 Intro' style chapter list for the description. Mod segments are labelled
    with the mod's name (and countdown rank) — falling back to the mod list when the
    segment carries no title — so the chapters are actually usable on YouTube instead
    of blank timestamps. `start_offset` accounts for a prepended cold-open teaser; the
    first chapter is clamped to 0:00 (YouTube requires it) so it covers the teaser.
    `extra_gaps` (segment_id -> seconds): see build_ass. `link_mods` appends each
    mod's Nexus page to its chapter line, so a viewer reading the timestamps has the
    download link right there (CHAPTER_LINK_SEP lets the description strip them again
    if the 5000-char cap needs the room)."""
    extra_gaps = extra_gaps or {}
    by_id = {m.mod_id: m for m in (mods or [])}
    n_mods = sum(1 for s in script.segments if getattr(s, "kind", "") == "mod")
    labels = {"hook": "Intro", "intro": "Intro", "outro": "Outro"}
    out, t, mod_i = [], float(start_offset), 0
    for idx, (seg, dur) in enumerate(zip(script.segments, durations)):
        tt = 0.0 if idx == 0 else t          # first chapter must be 0:00 for YouTube
        m_, s_ = int(tt // 60), int(tt % 60)
        kind = getattr(seg, "kind", "")
        label = (seg.title or "").strip()
        if kind == "mod":
            mod_i += 1
            mod = by_id.get(seg.mod_id)
            name = label or (mod.name if mod else f"Mod {mod_i}")
            name = _clean_chapter_name(name)
            rank = n_mods - mod_i + 1
            label = f"#{rank} {name}" if n_mods >= 3 else name
        elif not label:
            label = labels.get(kind, kind.title() or "Chapter")
        if link_mods and kind == "mod":
            url = getattr(by_id.get(seg.mod_id), "page_url", "")
            if url:
                # Bare host: YouTube still auto-links it, and the 12 chars saved per
                # line decide whether a long list's links fit the description cap.
                label += CHAPTER_LINK_SEP + re.sub(r"^https?://(www\.)?", "", url)
        out.append(f"{m_}:{s_:02d} {label}")
        t += dur + extra_gaps.get(seg.segment_id, 0.0)
    return out
