"""End-to-end orchestration: research -> script -> assets -> voice -> edit -> package.

Each stage writes its output to work/<slug>/state.json so stages can be re-run or
resumed independently. Run the whole thing with `skyrim-reviewer make`.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .config import active_profile, channel_config
from .models import Project, VideoFormat


def _slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def new_project(category_id: str, profile_name: str | None = None,
                fmt: str = "category_list", theme: str = "") -> Project:
    cfg = channel_config()
    name, profile = active_profile(cfg, override=profile_name)
    slug = f"{date.today().isoformat()}-{_slugify(category_id or theme or fmt)}-{name}"
    project = Project(
        slug=slug,
        category_id=category_id,
        theme=theme,
        format=VideoFormat(fmt),
        profile_name=name,
        profile=profile,
        workdir=str(Path("work") / slug),
    )
    Path(project.workdir).mkdir(parents=True, exist_ok=True)
    return project


def _save(project: Project) -> None:
    (Path(project.workdir) / "state.json").write_text(project.model_dump_json(indent=2))


def run(category_id: str, *, profile_name: str | None = None,
        fmt: str = "category_list", theme: str = "",
        next_topic: str = "", skip_render: bool = False) -> Project:
    from .assets import acquire_media
    from .edit.assemble import assemble_video
    from .edit.remotion_render import render_title_card
    from .research import research_category
    from .scripting import write_script
    from .thumbnail import make_thumbnail
    from .voice import get_provider

    cfg = channel_config()
    project = new_project(category_id, profile_name, fmt, theme)
    resolution = tuple(cfg["video"]["resolution"])

    cat = next((c for c in cfg["categories"] if c["id"] == category_id), None)
    category_title = cat["title"] if cat else (theme or "Best Skyrim Mods")

    # 1. Research
    print(f"[1/6] Researching best mods for '{category_id}'...")
    project.mods = research_category(category_id, project.profile.mods_per_video)
    _save(project)
    print(f"      Selected {len(project.mods)} mods.")

    # 2. Script
    print("[2/6] Writing narration script (Claude)...")
    project.script = write_script(
        project.mods, category_title=category_title, fmt=VideoFormat(fmt),
        profile=project.profile,
        next_topic=next_topic or "more game-changing Skyrim mods", theme=theme,
    )
    _save(project)
    print(f"      Title: {project.script.title}")

    # 3. Assets (permission-gated)
    print("[3/6] Acquiring permitted media + building credits...")
    acquire_media(project, resolution=resolution)
    _save(project)

    # 4. Voice
    print("[4/6] Narrating with the configured voice...")
    provider = get_provider()
    provider.narrate_script(project.script, Path(project.workdir) / "narration")
    _save(project)

    # 5. Package extras: Remotion title card + thumbnail
    print("[5/6] Rendering title card + thumbnail...")
    render_title_card(
        title=project.script.hook_line or category_title,
        subtitle=cfg["branding"]["watermark"],
        accent=cfg["branding"]["accent_color"],
        out_path=Path(project.workdir) / "remotion" / "title.mp4",
    )
    make_thumbnail(project, accent=cfg["branding"]["accent_color"])
    _save(project)

    # 6. Edit / assemble
    if skip_render:
        print("[6/6] Skipping final render (--skip-render).")
        return project
    print("[6/6] Assembling final video (Ken Burns, music, captions)...")
    assemble_video(project, accent=cfg["branding"]["accent_color"])
    _save(project)
    print(f"\nDone -> {project.output_path}")
    print(f"Thumbnail -> {project.thumbnail_path}")
    return project
