"""Command-line interface.

    skyrim-reviewer make weapons               # full pipeline, default (test) profile
    skyrim-reviewer make weapons --profile full
    skyrim-reviewer research weapons           # just print the ranked mods
    skyrim-reviewer script weapons             # research + script, no render
    skyrim-reviewer categories                 # list configured category buckets
"""
from __future__ import annotations

import typer

from .config import channel_config

app = typer.Typer(add_completion=False, help="AI Skyrim mod review video generator")


@app.command()
def categories(game: str = typer.Option(None, help="Nexus game domain, e.g. fallout4")):
    """List the configured evergreen category buckets."""
    if game:
        import os
        os.environ["MODREVIEWER_GAME"] = game
    for c in channel_config()["categories"]:
        typer.echo(f"  {c['id']:<12} {c['title']}")


@app.command()
def approve(value: str):
    """Approve a mod AUTHOR (name) or MOD ID (number) for media reuse.

    Use after an author permits showing their media (comment/DM/"free to use in
    videos with credit"). The footage stage then downloads that mod's image.
    """
    from .config import add_permission
    key = add_permission(value)
    typer.echo(f"Approved '{value}' -> {key}. The author will still be credited "
               f"on screen and in the description.")


@app.command(name="fetch-music")
def fetch_music():
    """Download the default royalty-free fantasy music set (Kevin MacLeod, CC BY 4.0)
    into music/. Tracks are credited automatically in each video's description."""
    from .edit.music import fetch_default_tracks
    paths = fetch_default_tracks()
    typer.echo(f"Fetched {len(paths)} tracks into music/. They'll be credited "
               f"(CC BY 4.0) in the video description automatically.")


@app.command()
def ideas(
    count: int = typer.Option(8, help="How many video ideas to generate"),
    live: bool = typer.Option(False, help="Attach real currently-trending mods (uses the API)"),
):
    """Generate viral-style video ideas modeled on top Skyrim-mod channels
    (config/reference_channels.yaml). Each idea prints a title, hook, the channels
    it's modeled on, and the exact command to produce it."""
    from .ideas import generate_ideas
    for i, idea in enumerate(generate_ideas(count, live=live), 1):
        typer.echo(f"\n{i}. {idea['title']}")
        typer.echo(f"   hook:    {idea['hook']}")
        typer.echo(f"   style:   {idea['format']}  (like {', '.join(idea['inspired_by']) or 'general'})")
        if idea["mods"]:
            typer.echo(f"   mods:    {', '.join(idea['mods'][:5])}")
        typer.echo(f"   make it: {idea['command']}")


@app.command()
def research(category: str, game: str = typer.Option(None, help="Nexus game domain, e.g. fallout4")):
    """Research + rank the best mods for a category (no script/render)."""
    if game:
        import os
        os.environ["MODREVIEWER_GAME"] = game
    from .research import research_category
    _, profile = _profile(None)
    mods = research_category(category, profile.mods_per_video)
    for i, m in enumerate(mods, 1):
        flag = "✓media" if m.allow_media_reuse else "placeholder"
        typer.echo(f"{i:>2}. [{m.score:5.2f}] {m.name}  by {m.uploaded_by or m.author} "
                   f"({m.endorsements} endo, {flag})")


@app.command()
def draft(
    category: str,
    profile: str = typer.Option(None, help="test | full"),
    fmt: str = typer.Option("category_list", help="category_list | transformation | weekly_roundup"),
    out: str = typer.Option(None, help="Output spec path (default scripts/<cat>-<profile>.yaml)"),
):
    """Live-research a category and write a script SKELETON (mods filled, narration
    blank) — then write the narration in chat and run `make --script <file>`."""
    from datetime import date
    from .config import channel_config
    from .research import research_category
    from .scripting.manual import spec_skeleton, write_spec
    name, prof = _profile(profile)
    cfg = channel_config()
    cat = next((c for c in cfg["categories"] if c["id"] == category), None)
    title = cat["title"] if cat else f"Best Skyrim {category} Mods"
    typer.echo(f"Researching '{category}' (deep scan, may take ~30-60s)...")
    mods = research_category(category, prof.mods_per_video)
    spec = spec_skeleton(mods, title=title, fmt=fmt, profile=prof)
    out = out or f"scripts/{category}-{name}-{date.today().isoformat()}.yaml"
    write_spec(spec, out)
    typer.echo(f"Wrote {out} with {len(mods)} mods. Fill in the narration, then:\n"
               f"  skyrim-reviewer make {category} --fmt {fmt} --script {out}")


@app.command()
def script(
    category: str,
    profile: str = typer.Option(None, help="test | full (default from config)"),
):
    """Research + write the narration script, print it (no render)."""
    from .pipeline import run
    project = run(category, profile_name=profile, skip_render=True)
    s = project.script
    typer.echo(f"\n=== {s.title} ===\n")
    for seg in s.segments:
        typer.echo(f"[{seg.kind}] {seg.title} (~{seg.target_seconds:.0f}s)")
        typer.echo(seg.narration + "\n")


@app.command()
def make(
    category: str = typer.Argument(..., help="Category id (see `categories`) or theme slug"),
    profile: str = typer.Option(None, help="test (5 min) | full (20 min)"),
    fmt: str = typer.Option("category_list", help="category_list | transformation | weekly_roundup"),
    theme: str = typer.Option("", help="For transformation videos, e.g. 'The Witcher'"),
    next_topic: str = typer.Option("", help="Tease this as next week's topic"),
    skip_render: bool = typer.Option(False, help="Stop before the final video render"),
    publish: bool = typer.Option(True, help="Upload video+title+thumb+description to GoFile"),
    game: str = typer.Option(None, help="Nexus game domain (e.g. fallout4, starfield). "
                             "Default: skyrim. See config/games.yaml"),
    script: str = typer.Option(
        None, "--script",
        help="Path to a chat-authored YAML script spec (skips research + Claude; "
             "no API keys needed)"),
):
    """Run the full pipeline: research -> script -> assets -> voice -> edit -> publish.

    Provide --script <file.yaml> to use a hand-written script (no API keys).
    On success the video, title, thumbnail and description are bundled to one GoFile
    link (disable with --no-publish).
    """
    if game:
        import os
        os.environ["MODREVIEWER_GAME"] = game
    from .pipeline import run
    run(category, profile_name=profile, fmt=fmt, theme=theme,
        next_topic=next_topic, skip_render=skip_render, script_spec=script,
        publish=publish)


@app.command()
def publish(slug: str):
    """Upload an already-rendered project's bundle (video + title + thumbnail +
    description) to a single GoFile folder. `slug` is the output file name without
    .mp4, e.g. 2026-06-03-weapons-test."""
    from pathlib import Path

    from .models import Project
    from .publish import publish_project
    # Find the saved project state by slug.
    state = next(Path("work").glob(f"*{slug}*/state.json"), None) \
        or Path("work") / slug / "state.json"
    if not Path(state).exists():
        typer.echo(f"No saved project for '{slug}' (looked for {state}).")
        raise typer.Exit(1)
    project = Project.model_validate_json(Path(state).read_text())
    link = publish_project(project)
    typer.echo(f"GoFile -> {link}" if link else "Upload failed.")


def _profile(name):
    from .config import active_profile
    return active_profile(override=name)


if __name__ == "__main__":
    app()
