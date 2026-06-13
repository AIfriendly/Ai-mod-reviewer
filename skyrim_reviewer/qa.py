"""Pre-publish quality gate.

Runs a battery of automated checks on a finished project + its rendered file and
returns a list of issues. The pipeline calls this before uploading: any ERROR blocks
the publish (unless overridden) so a broken or embarrassing video never ships.

Checks cover the things that actually go wrong in an automated channel:
  * narration: leftover URLs/markup, truncated final sentences, off-topic leaks from a
    mod's description (author dedications, donation/Discord begging), too-thin segments;
  * media: every featured mod has a real (non-placeholder) visual;
  * the rendered file: exists, has video+audio, sane duration, and a sane loudness;
  * packaging: no duplicate mod across the video, title length, non-empty description.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import Project


@dataclass
class Issue:
    level: str        # "error" | "warn"
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.code}: {self.message}"


# Phrases that mean a mod's summary leaked something off-topic into the narration.
_OFFTOPIC = re.compile(
    r"\b(dedicated to|in memory of|rest in peace|my (?:sister|brother|mother|father|"
    r"wife|husband|dog|cat)|patreon|ko-?fi|paypal|donat|discord\.gg|join my discord|"
    r"subscribe to my|please endorse|nexus mods account|trade ?mark)\b", re.I)
_URLISH = re.compile(r"https?://|www\.|\[/?[a-z]|&nbsp;|\bn/a\b", re.I)


def _probe(path: Path) -> dict:
    from .utils.ffmpeg import ffprobe_path
    out = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries",
         "format=duration:stream=codec_type", "-of", "json", str(path)],
        capture_output=True, text=True)
    try:
        return json.loads(out.stdout or "{}")
    except Exception:
        return {}


def _loudness(path: Path) -> float | None:
    """Integrated loudness (LUFS) of the final mix, or None if it can't be measured."""
    from .utils.ffmpeg import ffmpeg_path
    out = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-nostats", "-i", str(path),
         "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", out.stderr or "")
    return float(m[-1]) if m else None


def qa_project(project: Project, *, min_minutes: float = 7.0,
               min_words_per_mod: int = 30) -> list[Issue]:
    """Return all QA issues for a finished project (empty == clean)."""
    issues: list[Issue] = []
    script = project.script

    # --- Narration / script ------------------------------------------------
    seen_mods: dict[int, str] = {}
    for seg in script.segments:
        text = (seg.narration or "").strip()
        kind = getattr(seg, "kind", "")
        if kind == "mod":
            if seg.mod_id in seen_mods:
                issues.append(Issue("error", "dup_mod",
                    f"mod {seg.mod_id} appears more than once in this video"))
            seen_mods[seg.mod_id] = text
            wc = len(text.split())
            if wc < min_words_per_mod:
                issues.append(Issue("warn", "thin_segment",
                    f"mod {seg.mod_id} narration is only {wc} words"))
        if not text:
            issues.append(Issue("error", "empty_narration",
                f"{kind or 'segment'} has no narration"))
            continue
        if _URLISH.search(text):
            issues.append(Issue("error", "markup_leak",
                f"{kind} narration contains a URL/markup fragment: …"
                f"{_URLISH.search(text).group(0)!r}"))
        if _OFFTOPIC.search(text):
            issues.append(Issue("error", "offtopic_leak",
                f"{kind} narration leaked off-topic text: "
                f"…{_OFFTOPIC.search(text).group(0)!r}"))
        if text[-1] not in ".!?\"'":
            issues.append(Issue("warn", "truncated",
                f"{kind} narration may end mid-sentence: …{text[-40:]!r}"))

    # --- Media -------------------------------------------------------------
    for mod in project.mods:
        reals = [a for a in mod.media if a and a.local_path
                 and "placeholder" not in Path(a.local_path).name.lower()]
        if not reals:
            issues.append(Issue("warn", "placeholder_only",
                f"'{mod.name}' has no real media — showing a placeholder slate"))

    # --- Packaging ---------------------------------------------------------
    if not (script.description or "").strip():
        issues.append(Issue("warn", "no_description", "description is empty"))
    if len(script.title or "") > 100:
        issues.append(Issue("warn", "long_title",
            f"title is {len(script.title)} chars (YouTube truncates ~70)"))

    # --- Rendered file -----------------------------------------------------
    out = Path(project.output_path) if project.output_path else None
    if not out or not out.exists():
        issues.append(Issue("error", "no_output", "rendered video file is missing"))
        return issues
    info = _probe(out)
    codecs = {s.get("codec_type") for s in info.get("streams", [])}
    if "video" not in codecs:
        issues.append(Issue("error", "no_video_stream", "output has no video stream"))
    if "audio" not in codecs:
        issues.append(Issue("error", "no_audio_stream", "output has no audio stream"))
    try:
        dur = float(info.get("format", {}).get("duration", 0))
    except Exception:
        dur = 0.0
    if dur < min_minutes * 60:
        issues.append(Issue("warn", "short_video",
            f"video is {dur/60:.1f} min (target ≥ {min_minutes:.0f} min)"))
    lufs = _loudness(out)
    if lufs is None:
        issues.append(Issue("warn", "no_audio_measured", "could not measure loudness"))
    elif lufs > -12:
        issues.append(Issue("error", "too_loud", f"mix is {lufs:.1f} LUFS (too hot)"))
    elif lufs < -30:
        issues.append(Issue("error", "too_quiet",
            f"mix is {lufs:.1f} LUFS — likely near-silent audio"))
    return issues


def format_report(issues: list[Issue]) -> str:
    if not issues:
        return "QA: clean ✓"
    errs = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]
    lines = [f"QA: {len(errs)} error(s), {len(warns)} warning(s)"]
    lines += [f"  {i}" for i in issues]
    return "\n".join(lines)


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
