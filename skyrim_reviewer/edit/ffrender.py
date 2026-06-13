"""ffmpeg-native video assembly — the fast path.

Renders each segment's visual with ffmpeg filters (zoompan Ken Burns over a blurred
fill, trailer-montage intro, lower-thirds) instead of generating frames in Python with
moviepy. This runs in C across all cores (often faster than realtime) and uses NVENC
on a GPU box, turning a ~2-hour long-form render into minutes.

Produces the same look as edit/assemble.py. Selected via config channel.yaml
video.engine: ffmpeg (moviepy remains the fallback).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from ..models import Mod, Project, Script
from .captions import segment_durations, write_srt, youtube_chapters
from .lower_third import render_lower_third


def _ff() -> str:
    from ..utils.ffmpeg import ffmpeg_path
    return ffmpeg_path()


def _run(args: list[str]):
    subprocess.run(args, check=True, capture_output=True, text=True)


def _audio_dur(path: str) -> float:
    from ..voice.base import _audio_duration
    return _audio_duration(Path(path))


def _mod_by_id(mods, mid):
    return next((m for m in mods if m.mod_id == mid), None)


def _hook_heroes(project: Project, limit: int = 10) -> list[str]:
    """One striking main image per mod (most-endorsed first) for the cold-open montage."""
    out = []
    ranked = sorted(project.mods, key=lambda m: getattr(m, "endorsements", 0),
                    reverse=True)
    for mod in ranked:
        for a in mod.media:
            if a and a.local_path and Path(a.local_path).suffix.lower() in _IMG_EXT:
                out.append(a.local_path)
                break
        if len(out) >= limit:
            break
    return out


_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_VID_EXT = {".mp4", ".webm", ".mov", ".mkv"}


def _kenburns_segment(images: list[str], dur: float, size, fps: int,
                      lower_third: str | None, out: Path, fade_in: float = 0.0):
    """Render one mod segment: N fit-over-blur zoompan shots concatenated, with an
    optional lower-third overlay, sized to the frame, lasting exactly `dur`.

    `fade_in` adds a short fade-from-black at the segment start — a clean pattern
    interrupt that marks each new countdown entry (retention)."""
    W, H = size
    fw, fh = int(W * 0.92), int(H * 0.92)
    imgs = images or []
    n = max(1, min(len(imgs), 6)) if imgs else 1   # use up to 6 images per mod
    imgs = (imgs[:n] if imgs else [])
    per = dur / n
    frames = max(1, round(per * fps))

    ff = _ff()
    args = [ff, "-y", "-v", "error"]
    for img in imgs:
        args += ["-loop", "1", "-t", f"{per:.3f}", "-i", img]
    if lower_third:
        args += ["-i", lower_third]
    lt_idx = len(imgs)

    parts, labels = [], []
    moves = [(1.0, 1.05), (1.05, 1.0), (1.0, 1.04), (1.04, 1.0)]
    for k in range(n):
        z0, z1 = moves[k % len(moves)]
        zexpr = f"{z0}+({z1-z0})*on/{frames}"
        parts.append(
            f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=22,eq=brightness=-0.08,setsar=1,"
            f"trim=end_frame={frames},setpts=PTS-STARTPTS[bg{k}];"
            f"[{k}:v]scale={fw}:{fh}:force_original_aspect_ratio=decrease,setsar=1[ff{k}];"
            f"[ff{k}]zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':s={fw}x{fh}:fps={fps},"
            f"trim=end_frame={frames},setpts=PTS-STARTPTS[fz{k}];"
            f"[bg{k}][fz{k}]overlay=(W-w)/2:(H-h)/2:shortest=1[s{k}];")
        labels.append(f"[s{k}]")
    chain = "".join(parts) + "".join(labels) + f"concat=n={n}:v=1:a=0[vc];"
    if lower_third:
        chain += f"[vc][{lt_idx}:v]overlay=0:0[vo];"
    else:
        chain += "[vc]copy[vo];"
    if fade_in > 0:
        chain += f"[vo]fade=t=in:st=0:d={fade_in:.2f}[v]"
    else:
        chain += "[vo]copy[v]"
    args += ["-filter_complex", chain, "-map", "[v]", "-t", f"{dur:.3f}",
             "-r", str(fps), "-pix_fmt", "yuv420p", "-c:v", "libx264",
             "-preset", "veryfast", str(out)]
    _run(args)


def _video_segment(video: str, dur: float, size, fps: int,
                   lower_third: str | None, out: Path, fade_in: float = 0.0):
    """Render one mod segment from REAL author B-roll: cover-fill the clip to frame,
    loop if it's shorter than the segment, drop its audio, overlay the lower-third."""
    W, H = size
    ff = _ff()
    args = [ff, "-y", "-v", "error",
            "-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", video]
    if lower_third:
        args += ["-loop", "1", "-i", lower_third]
    chain = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"setsar=1,fps={fps},eq=brightness=-0.04:saturation=1.05[vc];")
    if lower_third:
        chain += "[vc][1:v]overlay=0:0[vo];"
    else:
        chain += "[vc]copy[vo];"
    if fade_in > 0:
        chain += f"[vo]fade=t=in:st=0:d={fade_in:.2f}[v]"
    else:
        chain += "[vo]copy[v]"
    args += ["-filter_complex", chain, "-map", "[v]", "-t", f"{dur:.3f}",
             "-r", str(fps), "-pix_fmt", "yuv420p", "-c:v", "libx264",
             "-preset", "veryfast", str(out)]
    _run(args)


def _hook_montage(images: list[str], dur: float, size, fps: int,
                  title_png: str, out: Path):
    """Cold open: a fast-cut, full-bleed montage of the actual best mod shots with the
    title overlaid for the first 5s. Real content + motion in the first seconds is the
    single biggest early-retention lever (most viewers leave in the first 60s)."""
    W, H = size
    imgs = [i for i in (images or []) if i][:10]
    if not imgs:
        return False
    n = len(imgs)
    per = max(0.45, dur / n)            # snappy cuts (~0.5s) for energy up front
    frames = max(1, round(per * fps))
    ff = _ff()
    args = [ff, "-y", "-v", "error"]
    for img in imgs:
        args += ["-loop", "1", "-t", f"{per:.3f}", "-i", img]
    args += ["-loop", "1", "-i", title_png]
    title_idx = n
    parts, labels = [], []
    for k in range(n):
        z0, z1 = (1.0, 1.08) if k % 2 == 0 else (1.08, 1.0)
        zexpr = f"{z0}+({z1-z0})*on/{frames}"
        parts.append(
            f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},eq=brightness=-0.04:saturation=1.08,setsar=1[c{k}];"
            f"[c{k}]zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps},"
            f"trim=end_frame={frames},setpts=PTS-STARTPTS[s{k}];")
        labels.append(f"[s{k}]")
    chain = "".join(parts) + "".join(labels) + f"concat=n={n}:v=1:a=0[mont];"
    chain += (f"[{title_idx}:v]format=rgba,fade=t=out:st=4.4:d=0.6:alpha=1[tt];"
              f"[mont][tt]overlay=0:0:enable='lt(t,5)',"
              f"fade=t=in:st=0:d=0.3,format=yuv420p[v]")
    args += ["-filter_complex", chain, "-map", "[v]", "-t", f"{dur:.3f}",
             "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", str(out)]
    _run(args)
    return True


def _title_segment(text_png: str, dur: float, size, fps: int, out: Path,
                   footage: list[str] | None):
    """Intro/hook/outro: trailer-montage (if footage) or static card, with a title
    PNG overlaid for the first 5s then faded."""
    W, H = size
    ff = _ff()
    args = [ff, "-y", "-v", "error"]
    if footage:
        # Concatenate cover-scaled trailer clips (skip first 8s of each), to ~dur.
        # Simple approach: loop the first trailer, cover-fill; montage variety comes
        # from the source already being cut footage.
        args += ["-ss", "8", "-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", footage[0]]
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1[bgv];")
    else:
        args += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
                 f"color=c=0x0b1018:s={W}x{H}:r={fps}"]
        base = "[0:v]setsar=1[bgv];"
    args += ["-loop", "1", "-i", text_png]            # title overlay (RGBA)
    # Show title for first 5s, fade out over 0.6s.
    chain = (base +
             f"[1:v]format=rgba,fade=t=out:st=4.4:d=0.6:alpha=1[tt];"
             f"[bgv][tt]overlay=0:0:enable='lt(t,5)',format=yuv420p[v]")
    args += ["-filter_complex", chain, "-map", "[v]", "-t", f"{dur:.3f}",
             "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", str(out)]
    _run(args)


def _save_overlay_png(title: str, subtitle: str, size, accent: str, out: Path):
    from PIL import Image
    from .titlecard import title_overlay_rgba
    Image.fromarray(title_overlay_rgba(title, subtitle, size, accent)).save(out)


def _concat_videos(paths: list[Path], out: Path):
    """Concatenate same-codec segment clips without re-encoding (concat demuxer)."""
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in paths))
    _run([_ff(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
          "-i", str(lst), "-c", "copy", str(out)])


def render_video_ffmpeg(project: Project, accent: str = "#d4af37",
                        music_dir: str = "music") -> Project:
    from ..config import channel_config
    from .music import pick_track, track_credit
    cfg = channel_config()["video"]
    size = tuple(cfg["resolution"])
    fps = int(cfg["fps"])
    script: Script = project.script
    workdir = Path(project.workdir)
    seg_dir = workdir / "ffsegs"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # Cinematic intro trailer footage (cached).
    footage = []
    try:
        from ..research.footage import fetch_trailers
        footage = fetch_trailers(channel_config()["channel"]["game_domain"])
    except Exception:
        footage = []

    spoken = [s for s in script.segments if (s.audio_path and Path(s.audio_path).exists())]
    # Countdown ranks: mod segments run from #N down to #1 in order.
    n_mods = sum(1 for s in spoken if getattr(s, "kind", "") == "mod")
    # Best hero shots (brightest first) for the cold-open montage.
    hook_heroes = _hook_heroes(project)
    mod_seen = 0
    seg_videos, seg_audios, durations = [], [], []
    for i, seg in enumerate(spoken):
        dur = _audio_dur(seg.audio_path)
        durations.append(dur)
        seg_audios.append(seg.audio_path)
        out = seg_dir / f"seg_{i:02d}.mp4"
        mod = _mod_by_id(project.mods, seg.mod_id) if seg.mod_id else None
        images = [a.local_path for a in (mod.media if mod else [])
                  if a and a.local_path and Path(a.local_path).suffix.lower() in _IMG_EXT]
        videos = [a.local_path for a in (mod.media if mod else [])
                  if a and a.local_path and getattr(a, "kind", "") == "video"
                  and Path(a.local_path).suffix.lower() in _VID_EXT
                  and Path(a.local_path).exists()]
        if mod and (images or videos):
            mod_seen += 1
            rank = (n_mods - mod_seen + 1) if n_mods >= 3 else None
            lt = seg_dir / f"lt_{i:02d}.png"
            render_lower_third(mod.name, mod.uploaded_by or mod.author or "Unknown",
                               size, lt, accent=accent, rank=rank)
            if videos:                       # real author B-roll beats Ken Burns stills
                _video_segment(videos[0], dur, size, fps, str(lt), out, fade_in=0.3)
            else:
                _kenburns_segment(images, dur, size, fps, str(lt), out, fade_in=0.3)
        else:
            kind = getattr(seg, "kind", "")
            if kind == "outro":
                title, sub = "Thanks for watching", "Like · Subscribe · Comment"
            elif kind == "intro":
                title, sub = script.title, getattr(script, "hook_line", "") or ""
            else:
                title, sub = (getattr(script, "hook_line", "") or script.title), ""
            png = seg_dir / f"title_{i:02d}.png"
            _save_overlay_png(title, sub, size, accent, png)
            # Cold open (hook): fast montage of real mod footage; fall back to trailer.
            if kind == "hook" and hook_heroes and \
                    _hook_montage(hook_heroes, dur, size, fps, str(png), out):
                pass
            else:
                _title_segment(str(png), dur, size, fps, out,
                               footage if kind in ("hook", "intro") else None)
        seg_videos.append(out)

    # Concat visuals (no re-encode).
    video_only = seg_dir / "_video.mp4"
    _concat_videos(seg_videos, video_only)

    # Animated captions (burned in) + a whoosh sting at each mod reveal.
    total_dur = sum(durations)
    mod_starts, acc = [], 0.0
    for seg, d in zip(spoken, durations):
        if getattr(seg, "kind", "") == "mod":
            mod_starts.append(acc)
        acc += d
    ass_path = None
    if cfg.get("captions", True):
        from .captions import build_ass
        ass_path = build_ass(spoken, durations, size, seg_dir / "captions.ass", accent)
    sfx_path = None
    if cfg.get("sfx", True):
        try:
            from .sfx import build_sfx_track
            sfx_path = build_sfx_track(mod_starts, total_dur, seg_dir / "sfx.wav")
        except Exception:
            sfx_path = None

    # Build narration (concat) + ducked music (+ SFX), then mux over the video,
    # burning captions in if enabled.
    ff = _ff()
    args = [ff, "-y", "-v", "error", "-i", str(video_only)]
    for a in seg_audios:
        args += ["-i", a]
    track = pick_track(music_dir)
    music_credit = track_credit(track)
    n_a = len(seg_audios)
    fc = ""
    for j in range(n_a):
        fc += f"[{j+1}:a]aresample=44100,aformat=channel_layouts=stereo[na{j}];"
    fc += "".join(f"[na{j}]" for j in range(n_a)) + f"concat=n={n_a}:v=0:a=1[narr];"
    next_idx = n_a + 1
    if track:
        args += ["-stream_loop", "-1", "-i", track]
        mi = next_idx
        next_idx += 1
        # Music bed sits well UNDER the narration: normalise to a quiet target, then
        # duck further under the voice via sidechain compression (no makeup gain). The
        # baseline level is configurable (video.music_lufs, default -26 LUFS).
        music_lufs = cfg.get("music_lufs", -26)
        fc += (f"[narr]asplit=2[narrA][narrB];"
               f"[{mi}:a]aresample=44100,aformat=channel_layouts=stereo,"
               f"loudnorm=I={music_lufs}:TP=-3:LRA=11[mbase];"
               f"[mbase][narrB]sidechaincompress=threshold=0.05:ratio=12:attack=5:"
               f"release=350:makeup=1[mduck];"
               f"[narrA][mduck]amix=inputs=2:duration=first:normalize=0[premix]")
    else:
        fc += "[narr]anull[premix]"
    if sfx_path:
        args += ["-i", str(sfx_path)]
        si = next_idx
        fc += (f";[{si}:a]aresample=44100,aformat=channel_layouts=stereo[sfxa];"
               f"[premix][sfxa]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        fc += ";[premix]anull[aout]"
    amap = "[aout]"
    # Video chain: burn captions, else pass through (re-encode either way once captions
    # are on; without captions we copy for speed).
    if ass_path:
        esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
        fc += f";[0:v]subtitles='{esc}'[vout]"
        vmap, vcopy = "[vout]", False
    else:
        vmap, vcopy = "0:v", True
    from .assemble import _encode_opts
    codec, preset, threads, extra = _encode_opts()
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{project.slug}.mp4"
    args += ["-filter_complex", fc, "-map", vmap, "-map", amap]
    if vcopy:
        args += ["-c:v", "copy"]
    else:
        args += ["-c:v", codec, "-preset", preset, *extra, "-pix_fmt", "yuv420p"]
        if threads:
            args += ["-threads", str(threads)]
    args += ["-c:a", "aac", "-shortest", str(out_path)]
    _run(args)

    # Sidecar artefacts (same as moviepy path).
    durs = segment_durations(script)
    write_srt(script, durs, out_dir / f"{project.slug}.srt")
    script.chapters = youtube_chapters(script, durs)
    from ..branding import make_description
    wm = ""
    try:
        wm = channel_config()["branding"].get("watermark", "")
    except Exception:
        pass
    desc = make_description(project, music_credit=music_credit, watermark=wm,
                            next_topic=getattr(project, "next_topic", "") or "")
    (out_dir / f"{project.slug}.description.txt").write_text(desc, encoding="utf-8")
    project.output_path = str(out_path)
    return project
