"""Assemble the final video.

Per segment: Ken-Burns visual (or mod video) sized to the frame, the narration
audio laid on top, and a credit lower-third for mod segments. Segments are
concatenated, a ducked music bed is mixed under everything, and the result is
written to output/<slug>.mp4. Title cards / intro come from Remotion (rendered
separately) and are prepended if present.
"""
from __future__ import annotations

from pathlib import Path

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
    seg_clips = []
    for seg, dur in zip(script.segments, durations):
        mod = _mod_by_id(project.mods, seg.mod_id) if seg.mod_id else None
        media_paths = [a.local_path for a in (mod.media if mod else []) if a and a.local_path]
        visual = clip_for_segment(media_paths, dur, size, fps=fps, shot_seconds=shot_seconds)

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

    # Music bed, ducked under the narration.
    bed = music_bed(video.duration, music_dir=music_dir)
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

    # Sidecar artefacts: subtitles + accurate chapters.
    write_srt(script, durations, out_dir / f"{project.slug}.srt")
    script.chapters = youtube_chapters(script, durations)
    (out_dir / f"{project.slug}.description.txt").write_text(
        script.title + "\n\n" + script.description + "\n\nChapters:\n" +
        "\n".join(script.chapters), encoding="utf-8")

    project.output_path = str(out_path)
    return project


def channel_video_cfg() -> dict:
    from ..config import channel_config
    return channel_config()["video"]


def project_resolution(project: Project) -> list[int]:
    from ..config import channel_config
    return channel_config()["video"]["resolution"]


def project_fps(project: Project) -> int:
    from ..config import channel_config
    return channel_config()["video"]["fps"]
