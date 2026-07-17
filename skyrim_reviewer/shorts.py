"""Vertical YouTube Shorts pipeline.

Spotlights ONE mod in a punchy ~30-45s vertical (1080x1920) clip that funnels viewers
to the full long-form video. Reuses the long-form building blocks — the cloned clarity
voice, the cover-crop zoom motion, burned animated captions, and the rotating music bed
— but in a 9:16 frame at Shorts length.

Build one from any full-video spec (it borrows that video's #1 mod + its already-scraped
media) via `make_short(spec_path=...)`, or from a live Project. Output is an mp4 plus a
Shorts-optimised title/description/tags bundle.
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import Project, Script, Segment, VideoFormat

VERTICAL = (1080, 1920)
FPS = 30

# Category-specific opening hooks (first ~2s pattern-interrupt line).
_HOOKS = {
    "new_lands": "This Skyrim mod hides a whole new land in your game.",
    "quests": "This Skyrim quest mod feels like official DLC.",
    "adventures": "This Skyrim mod adds a whole new adventure.",
    "followers": "This might be the best Skyrim follower mod yet.",
    "magic": "This Skyrim magic mod is genuinely insane.",
    "graphics": "This is what modded Skyrim looks like in 2026.",
    "weapons": "This Skyrim weapon mod hits different.",
    "armor": "This Skyrim armor mod looks unreal.",
    "gameplay": "This mod completely changes how Skyrim plays.",
}


def _first_sentences(text: str, max_words: int) -> str:
    """The opening of a mod's pitch, trimmed to whole sentences under max_words."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    out, n = [], 0
    for sent in re.split(r"(?<=[.!?]) ", text):
        w = len(sent.split())
        if out and n + w > max_words:
            break
        out.append(sent)
        n += w
    return " ".join(out) or text


def _short_script(mod, category_id: str, channel: str, max_words: int,
                  source_pitch: str = "", standalone: bool = False) -> Script:
    """A 3-beat Short: hook -> condensed mod pitch -> CTA. When `standalone`, the Short
    is its OWN mini-review (its own fresh mod), so the CTA points at the channel, not a
    'full video'."""
    hook = _HOOKS.get(category_id, "You need to see this Skyrim mod.")
    pitch = _first_sentences(source_pitch or mod.summary, max_words)
    if not pitch:
        pitch = f"{mod.name} is one you probably missed — and it's completely free on Nexus."
    author = mod.uploaded_by or mod.author or "its author"
    if standalone:
        cta = (f"That's {mod.name}, by {author} — free on Nexus, link in the description. "
               f"Follow {channel} for a new Skyrim mod every day.")
        title = f"You NEED this Skyrim Mod — {mod.name} #shorts"
    else:
        cta = (f"That's {mod.name}, by {author}. Ten more like it in the full video — "
               f"follow {channel}.")
        title = f"{mod.name} — Skyrim Mod #Shorts"
    segs = [
        Segment(segment_id="hook", kind="hook", narration=hook, title=""),
        Segment(segment_id="pitch", kind="mod", narration=pitch, title=mod.name,
                mod_id=mod.mod_id),
        Segment(segment_id="cta", kind="outro", narration=cta, title=""),
    ]
    return Script(title=title, format=VideoFormat.category_list, hook_line=hook,
                  segments=segs)


def _mod_images(mod) -> list[str]:
    """The mod's downloadable, non-placeholder screenshots (best-exposed first)."""
    from .thumbnail.generate import _hero_quality
    imgs = [a.local_path for a in mod.media
            if a and a.local_path and a.kind == "image"
            and "placeholder" not in a.local_path and Path(a.local_path).exists()]
    return sorted(imgs, key=_hero_quality, reverse=True)


def _cta_card(channel: str, accent: str, out: Path, standalone: bool = False) -> str:
    """A final full-frame vertical CTA slate. Standalone Shorts push a follow, not a
    'watch the full video'."""
    from PIL import Image, ImageDraw
    from .thumbnail.generate import _font, _hex
    W, H = VERTICAL
    img = Image.new("RGB", VERTICAL, (12, 15, 21))
    d = ImageDraw.Draw(img)
    acc = _hex(accent)
    top, bot = ("MORE MODS", "EVERY DAY") if standalone else ("WATCH THE", "FULL VIDEO")
    d.text((W // 2, H // 2 - 140), top, font=_font(84), fill="white",
           anchor="mm", stroke_width=4, stroke_fill="black")
    d.text((W // 2, H // 2 - 30), bot, font=_font(120), fill=acc,
           anchor="mm", stroke_width=5, stroke_fill="black")
    d.text((W // 2, H // 2 + 120), channel, font=_font(70), fill="white",
           anchor="mm", stroke_width=4, stroke_fill="black")
    d.rounded_rectangle([W // 2 - 240, H // 2 + 220, W // 2 + 240, H // 2 + 330],
                        radius=24, fill=acc)
    d.text((W // 2, H // 2 + 275), "SUBSCRIBE", font=_font(56), fill=(12, 14, 18),
           anchor="mm")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return str(out)


def make_short(spec_path: str | None = None, project: Project | None = None,
               category: str | None = None, out_dir: str = "output",
               music_dir: str = "music", accent: str = "#d4af37", max_words: int = 60,
               cta_seconds: float = 2.5) -> dict:
    """Render a vertical Short. Three modes:
      • category="adventures"  -> STANDALONE: discovers its OWN fresh, never-featured
        mod and reviews it as a self-contained Short (records it so it's never reused).
      • spec_path=<yaml>       -> companion Short from that video's #1 pick.
      • project=<Project>      -> companion Short from an in-memory project.
    Returns {video, slug, title, description, tags, mod, duration, standalone}."""
    from .config import active_profile, channel_config
    from .assets import acquire_media
    from .voice import get_provider
    from .edit.ffrender import _zoom_segment, _ff, _audio_dur
    from .edit.captions import build_ass
    from .edit.music import build_music_bed, pick_track

    cfg = channel_config()
    channel = cfg.get("channel", {}).get("name", "@ModVault")
    category_id = ""
    standalone = bool(category) and project is None and spec_path is None

    # 1. Resolve the mods + media.
    if standalone:
        # Discover ONE fresh, never-featured mod in this category — its own content.
        from .scripting.autospec import autospec as _autospec
        from .scripting import apply_spec
        _, profile = active_profile(override="full")
        spec = _autospec(category, count=1)          # excludes history + galleries baked
        category_id = category
        mid = spec["mods"][0]["mod_id"]
        slug = f"short-{category}-{mid}"
        project = Project(slug=slug, workdir=f"work/{slug}", mods=[], profile=profile,
                          category_id=category_id)
        apply_spec(project, spec)
        project.slug = slug
        project.workdir = f"work/{slug}"
        Path(project.workdir).mkdir(parents=True, exist_ok=True)
    elif project is None:
        if not spec_path:
            raise ValueError("make_short needs spec_path, project, or category")
        from .scripting import apply_spec, load_spec
        _, profile = active_profile(override="full")
        spec = load_spec(spec_path)
        category_id = spec.get("category_id", "") or ""
        slug = f"short-{Path(spec_path).stem}"
        project = Project(slug=slug, workdir=f"work/{slug}", mods=[], profile=profile,
                          category_id=category_id)
        apply_spec(project, spec)
        # apply_spec adopts the spec's own `slug:` — force the short slug back so the
        # Short never writes over the full video's output/work paths.
        project.slug = slug
        project.workdir = f"work/{slug}"
        Path(project.workdir).mkdir(parents=True, exist_ok=True)
    else:
        category_id = project.category_id or ""
        slug = project.slug

    # each mod's full-video narration, so the Short's pitch can borrow from it
    pitches: dict[int, str] = {}
    if project.script:
        for seg in project.script.segments:
            if seg.mod_id and seg.narration:
                pitches.setdefault(seg.mod_id, seg.narration)

    # Pull the video's MOST VIRAL part into the Short: its #1 pick — the countdown
    # climax (the last mod segment), the moment the whole video builds toward. Fall
    # back to the highest-endorsed mods that actually have usable media. Only acquire
    # media for these top candidates, not the whole 10-mod gallery.
    climax_id = None
    if project.script:
        mod_segs = [s for s in project.script.segments if s.kind == "mod" and s.mod_id]
        if mod_segs:
            climax_id = mod_segs[-1].mod_id
    ranked = sorted(project.mods, key=lambda m: getattr(m, "endorsements", 0),
                    reverse=True)
    order = []
    if climax_id:
        climax = next((m for m in project.mods if m.mod_id == climax_id), None)
        if climax:
            order.append(climax)
    order += [m for m in ranked if m not in order]
    mod, images = None, []
    for cand in order[:5]:
        one = Project(slug=project.slug, workdir=project.workdir, mods=[cand],
                      profile=project.profile, category_id=category_id)
        acquire_media(one, resolution=VERTICAL)
        imgs = _mod_images(cand)
        if imgs:
            mod, images = cand, imgs
            break
    if mod is None:
        raise RuntimeError("no mod with usable media to build a Short from")

    workdir = Path(project.workdir); workdir.mkdir(parents=True, exist_ok=True)
    seg_dir = workdir / "short"; seg_dir.mkdir(exist_ok=True)

    # 2. Script + narration (cloned clarity voice, pronunciation + mastering applied).
    #    Standalone Shorts pitch from the mod's own summary (not the templated
    #    autospec narration); companion Shorts borrow the long video's narration.
    script = _short_script(mod, category_id, channel, max_words,
                           source_pitch="" if standalone else pitches.get(mod.mod_id, ""),
                           standalone=standalone)
    provider = get_provider()
    provider.narrate_script(script, seg_dir / "narration")
    spoken = [s for s in script.segments if s.audio_path]
    durations = [float(s.audio_seconds or _audio_dur(s.audio_path)) for s in spoken]
    narr_dur = sum(durations)

    # 3. Vertical visual: cover-crop zoom montage over the mod's best shots for the
    #    whole narration, then a CTA slate tail.
    ff = _ff()
    body = seg_dir / "body.mp4"
    _zoom_segment(images, narr_dur, VERTICAL, FPS, None, body, fade_in=0.2,
                  target_shot=3.2)
    cta_png = _cta_card(channel, accent, seg_dir / "cta.png", standalone=standalone)
    cta_mp4 = seg_dir / "cta.mp4"
    _run = __import__("subprocess").run
    _run([ff, "-y", "-v", "error", "-loop", "1", "-t", f"{cta_seconds:.2f}",
          "-i", cta_png, "-vf", f"scale={VERTICAL[0]}:{VERTICAL[1]},fps={FPS},"
          f"format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(cta_mp4)],
         check=True)
    video_only = seg_dir / "video_only.mp4"
    concat_txt = seg_dir / "concat.txt"
    concat_txt.write_text(f"file '{body.resolve()}'\nfile '{cta_mp4.resolve()}'\n")
    _run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
          "-c", "copy", str(video_only)], check=True)

    total_dur = narr_dur + cta_seconds

    # 4. Captions (big, burned) over the narrated portion only.
    ass_path = build_ass(spoken, durations, VERTICAL, seg_dir / "captions.ass", accent)

    # 5. Mux: narration concat + ducked rotating music, burn captions, master to -14 LUFS.
    track, _ = build_music_bed(total_dur, seg_dir / "music_bed.m4a", music_dir)
    if not track:
        track = pick_track(music_dir)
    args = [ff, "-y", "-v", "error", "-i", str(video_only)]
    for s in spoken:
        args += ["-i", s.audio_path]
    n_a = len(spoken)
    fc = ""
    for j in range(n_a):
        fc += f"[{j+1}:a]aresample=44100,aformat=channel_layouts=stereo[na{j}];"
    fc += "".join(f"[na{j}]" for j in range(n_a)) + f"concat=n={n_a}:v=0:a=1[narr];"
    if track:
        args += ["-stream_loop", "-1", "-i", str(track)]
        mi = n_a + 1
        fc += (f"[narr]asplit=2[nA][nB];"
               f"[{mi}:a]aresample=44100,aformat=channel_layouts=stereo,"
               f"loudnorm=I=-26:TP=-3:LRA=11[mb];"
               f"[mb][nB]sidechaincompress=threshold=0.05:ratio=12:attack=5:"
               f"release=350:makeup=1[md];"
               f"[nA][md]amix=inputs=2:duration=first:normalize=0[premix]")
    else:
        fc += "[narr]anull[premix]"
    fc += ";[premix]loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
    esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
    fc += (f";[0:v]eq=contrast=1.06:saturation=1.12,"
           f"subtitles='{esc}'[vout]")
    out_dir_p = Path(out_dir); out_dir_p.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir_p / f"{project.slug}.mp4"
    args += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
             "-t", f"{total_dur:.2f}", "-r", str(FPS), "-c:v", "libx264",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-b:a", "160k", "-movflags", "+faststart", str(out_mp4)]
    _run(args, check=True)

    # 6. Shorts metadata.
    tags = ["skyrim", "skyrim mods", "skyrim shorts", mod.name.lower(),
            f"skyrim {category_id.replace('_', ' ')}", "modded skyrim"]
    tail = (f"Follow {channel} for a new free Skyrim mod every day."
            if standalone else f"Full video on the channel — {channel}")
    desc = (f"{mod.name} by {mod.uploaded_by or mod.author}\n{mod.page_url}\n\n"
            f"{tail}\n#skyrim #skyrimmods #shorts")
    (out_dir_p / f"{project.slug}.title.txt").write_text(
        f"{script.title}\n", encoding="utf-8")
    (out_dir_p / f"{project.slug}.description.txt").write_text(desc, encoding="utf-8")
    (out_dir_p / f"{project.slug}.tags.txt").write_text(", ".join(tags), encoding="utf-8")
    # A standalone Short IS its own video about a real mod — record it so no long video
    # (or future Short) ever re-uses that mod.
    if standalone:
        try:
            from .history import record_video
            record_video(project)
        except Exception:
            pass
    return {"video": str(out_mp4), "slug": project.slug, "title": script.title,
            "description": desc, "tags": tags, "mod": mod.name,
            "duration": round(total_dur, 1), "standalone": standalone}
