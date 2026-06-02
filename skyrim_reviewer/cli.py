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
def categories():
    """List the configured evergreen category buckets."""
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


@app.command()
def research(category: str):
    """Research + rank the best mods for a category (no script/render)."""
    from .research import research_category
    _, profile = _profile(None)
    mods = research_category(category, profile.mods_per_video)
    for i, m in enumerate(mods, 1):
        flag = "✓media" if m.allow_media_reuse else "placeholder"
        typer.echo(f"{i:>2}. [{m.score:5.2f}] {m.name}  by {m.uploaded_by or m.author} "
                   f"({m.endorsements} endo, {flag})")


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
    script: str = typer.Option(
        None, "--script",
        help="Path to a chat-authored YAML script spec (skips research + Claude; "
             "no API keys needed)"),
):
    """Run the full pipeline: research -> script -> assets -> voice -> edit.

    Provide --script <file.yaml> to use a hand-written script (no API keys).
    """
    from .pipeline import run
    run(category, profile_name=profile, fmt=fmt, theme=theme,
        next_topic=next_topic, skip_render=skip_render, script_spec=script)


def _profile(name):
    from .config import active_profile
    return active_profile(override=name)


if __name__ == "__main__":
    app()
