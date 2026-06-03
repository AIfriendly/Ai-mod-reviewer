"""Assemble the final video.

Per segment: Ken-Burns visual (or mod video) sized to the frame, the narration
audio laid on top, and a credit lower-third for mod segments. Segments are
concatenated, a ducked music bed is mixed under everything, and the result is
written to output/<slug>.mp4. Title cards / intro come from Remotion (rendered
separately) and are prepended if present.
"""
from __future__ import annotations

from pathlib import Path

from . import pil_compat  # noqa: F401  (restores PIL.Image.ANTIALIAS for MoviePy 1.x)
from ..models import Mod, Project, Script
from ..utils.ffmpeg import configure_moviepy
from .captions import segment_durations, write_srt, youtube_chapters
from .kenburns import clip_for_segment
from .lower_third import render_lower_third
from .music import music_bed


def _mod_by_id(mods: list[Mod], mod_id) -> Mod | None:
    return next((m for m in mods if m.mod_id == mod_id), None)


def assemble_video(project: Project, accent: str = "#d4af37",
                   music_dir: str = "music") -> Project:
    configure_moviepy()
    from moviepy.audio.fx.all import volumex
    from moviepy.editor import (AudioFileClip, CompositeAudioClip,
                                CompositeVideoClip, ImageClip,
                                concatenate_videoclips)

    script: Script = project.script
    size = tuple(project_resolution(project))
    fps = project_fps(project)
    workdir = Path(project.workdir)
    overlays_dir = workdir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    durations = segment_durations(script)
    shot_seconds = channel_video_cfg().get("shot_seconds", 18.0)
    # A backdrop for the title/intro/outro cards: the first available mod image.
    backdrop = next((a.local_path for m in project.mods for a in m.media
                     if a and a.local_path), None)
    # Cinematic intro: official gameplay-trailer B-roll behind the title (cached).
    # Multiple trailers are pooled so the intro montage cuts between different footage.
    footage: list[str] = []
    if channel_video_cfg().get("intro_footage", True):
        try:
            from ..config import channel_config
            from ..research.footage import fetch_trailers
            footage = fetch_trailers(channel_config()["channel"]["game_domain"])
        except Exception:
            footage = []
    seg_clips = []
    for seg, dur in zip(script.segments, durations):
        mod = _mod_by_id(project.mods, seg.mod_id) if seg.mod_id else None
        media_paths = [a.local_path for a in (mod.media if mod else []) if a and a.local_path]
        if mod and media_paths:
            visual = clip_for_segment(media_paths, dur, size, fps=fps,
                                      shot_seconds=shot_seconds)
        elif footage and (getattr(seg, "kind", "") in ("hook", "intro")):
            # Cold open: cinematic Skyrim trailer footage behind the title + hook VO.
            visual = _intro_footage_clip(seg, script, dur, size, fps, accent, footage)
        else:
            # Other non-mod segments (outro) -> a title card, not a blank.
            visual = _card_clip(seg, script, dur, size, fps, accent, backdrop)

        layers = [visual]
        if mod:  # credit lower-third on screen
            lt_path = overlays_dir / f"{seg.segment_id}_lt.png"
            render_lower_third(mod.name, mod.uploaded_by or mod.author or "Unknown",
                               size, lt_path, accent=accent)
            layers.append(ImageClip(str(lt_path)).set_duration(dur))

        clip = CompositeVideoClip(layers, size=size).set_duration(dur)
        if seg.audio_path and Path(seg.audio_path).exists():
            clip = clip.set_audio(AudioFileClip(seg.audio_path))
        seg_clips.append(clip)

    video = concatenate_videoclips(seg_clips, method="compose")

    # Music bed, ducked under the narration. Record the track so we can credit it
    # (CC BY tracks require attribution in the description).
    from .music import pick_track, track_credit
    chosen = pick_track(music_dir)
    music_attribution = track_credit(chosen)
    bed = music_bed(video.duration, music_dir=music_dir, track=chosen)
    if bed is not None and video.audio is not None:
        video = video.set_audio(CompositeAudioClip([video.audio, bed]))
    elif bed is not None:
        video = video.set_audio(bed)

    # Prepend a Remotion-rendered intro/title card if it was built.
    intro = workdir / "remotion" / "title.mp4"
    if intro.exists():
        from moviepy.editor import VideoFileClip
        intro_clip = VideoFileClip(str(intro)).resize(newsize=size)
        video = concatenate_videoclips([intro_clip, video], method="compose")

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{project.slug}.mp4"
    video.write_videofile(
        str(out_path), fps=fps, codec="libx264", audio_codec="aac",
        threads=4, preset="medium",
    )

    # Sidecar artefacts: subtitles + accurate chapters + channel-style description.
    write_srt(script, durations, out_dir / f"{project.slug}.srt")
    script.chapters = youtube_chapters(script, durations)
    from ..branding import make_description
    watermark = ""
    try:
        from ..config import channel_config
        watermark = channel_config()["branding"].get("watermark", "")
    except Exception:
        pass
    description = make_description(
        project, music_credit=music_attribution, watermark=watermark,
        next_topic=getattr(project, "next_topic", "") or "")
    (out_dir / f"{project.slug}.description.txt").write_text(description, encoding="utf-8")

    project.output_path = str(out_path)
    return project


def _fill(clip, size):
    """Scale + center-crop a clip to fill the frame (no bars)."""
    from moviepy.video.fx.all import crop, resize
    W, H = size
    scale = max(W / clip.w, H / clip.h)
    clip = resize(clip, scale)
    return crop(clip, width=W, height=H, x_center=clip.w / 2, y_center=clip.h / 2)


def _intro_footage_clip(seg, script: Script, dur: float, size, fps: int,
                        accent: str, footage_paths: list[str], cut_seconds: float = 5.0):
    """Trailer B-roll edited as a montage — a DIFFERENT clip every ~`cut_seconds` —
    with the title + scrim overlaid. Pulls distinct 5s shots from the pooled trailers."""
    import hashlib

    from moviepy.editor import (CompositeVideoClip, ImageClip, VideoFileClip,
                                concatenate_videoclips)
    from .titlecard import title_overlay_rgba

    # Collect candidate non-overlapping shots (start offsets) across all trailers,
    # skipping each trailer's opening (publisher logos / ESRB rating cards) and any
    # near-black shots (fade transitions / title cards).
    skip_intro = 8.0
    shots = []  # (path, start)
    for path in footage_paths:
        try:
            clip = VideoFileClip(path)
            d = clip.duration
        except Exception:
            continue
        t = skip_intro if d > skip_intro + cut_seconds else 0.0
        while t + cut_seconds <= d + 0.01:
            try:
                bright = float(clip.get_frame(min(t + 0.5, d)).mean())
            except Exception:
                bright = 0.0
            if bright >= 28:                 # drop black fades / dark logo screens
                shots.append((path, t))
            t += cut_seconds
    if not shots:
        return _card_clip(seg, script, dur, size, fps, accent,
                          footage_paths[0] if footage_paths else None)

    # Deterministic shuffle so consecutive cuts come from varied points/trailers.
    rng = __import__("random").Random(int(hashlib.md5(script.title.encode()).hexdigest(), 16))
    rng.shuffle(shots)

    n_cuts = max(1, int(round(dur / cut_seconds)))
    pieces, used = [], 0.0
    for i in range(n_cuts):
        path, start = shots[i % len(shots)]
        seg_dur = min(cut_seconds, dur - used)
        if seg_dur <= 0.05:
            break
        sub = VideoFileClip(path).without_audio().subclip(start, start + seg_dur)
        pieces.append(_fill(sub, size))
        used += seg_dur
    montage = concatenate_videoclips(pieces, method="compose").set_duration(dur)

    title = getattr(script, "hook_line", "") or script.title
    subtitle = script.title if getattr(seg, "kind", "") == "intro" else ""
    overlay = ImageClip(title_overlay_rgba(title, subtitle, size, accent)).set_duration(dur)
    return (CompositeVideoClip([montage, overlay], size=size)
            .set_duration(dur).set_fps(fps))


def _card_clip(seg, script: Script, dur: float, size, fps: int, accent: str,
               backdrop: str | None):
    """Title/intro/outro card with a gentle zoom, so non-mod segments aren't blank."""
    from moviepy.editor import ImageClip
    from .titlecard import title_card_array

    kind = getattr(seg, "kind", "") or ""
    if kind == "outro":
        title, subtitle = "Thanks for watching", "Like · Subscribe · Comment"
    elif kind == "intro":
        title, subtitle = script.title, getattr(script, "hook_line", "") or ""
    else:  # hook / cold open
        title = getattr(script, "hook_line", "") or script.title
        subtitle = ""

    arr = title_card_array(title, subtitle, size, accent=accent, bg_image=backdrop)
    clip = ImageClip(arr).set_duration(dur).set_fps(fps)
    # subtle push-in
    clip = clip.resize(lambda t: 1.0 + 0.04 * (t / dur if dur else 0))
    clip = clip.set_position(("center", "center"))
    from moviepy.editor import CompositeVideoClip
    return CompositeVideoClip([clip], size=size).set_duration(dur)


def channel_video_cfg() -> dict:
    from ..config import channel_config
    return channel_config()["video"]


def project_resolution(project: Project) -> list[int]:
    from ..config import channel_config
    return channel_config()["video"]["resolution"]


def project_fps(project: Project) -> int:
    from ..config import channel_config
    return channel_config()["video"]["fps"]
