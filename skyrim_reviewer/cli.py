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


@app.command(name="export-script")
def export_script(
    category: str = typer.Argument(..., help="Category id (for the slug)"),
    script: str = typer.Option(..., "--script", help="YAML script spec to export"),
    ref: str = typer.Option("voices/clone/ref_primary.wav", help="Voice reference clip"),
    ref_text: str = typer.Option("", help="Transcript of the reference (optional)"),
):
    """Export a narration kit (segment texts + your voice reference + Kaggle notebook)
    to run the F5 voiceover on a free GPU. Produces output/<slug>_narration_kit.zip."""
    from .pipeline import new_project
    from .publish.narration import export_narration_kit
    from .scripting import apply_spec, load_spec
    project = new_project(category, "test", "category_list")
    apply_spec(project, load_spec(script))
    kit = export_narration_kit(project, ref_audio=ref, ref_text=ref_text)
    typer.echo(f"Narration kit -> {kit}/ (and {kit}.zip)\n"
               f"Upload the .zip to Kaggle as a Dataset, run f5_narrate.ipynb on a GPU, "
               f"then put the returned wavs in work/narration/ and assemble with "
               f"`make {category} --script {script} --voice prerecorded`.")


@app.command(name="voice-prep")
def voice_prep(
    source: str = typer.Argument(..., help="Audio/video file with your voice"),
    out: str = typer.Option("voices/clone/ref_primary.wav", help="Output reference wav"),
    start: float = typer.Option(0.0, help="Start seconds to clip from"),
    seconds: float = typer.Option(12.0, help="Clip length (F5 wants a clean ≤15s ref)"),
):
    """Prepare an F5-TTS reference clip: clip + resample to 24kHz mono + loudness
    normalize. Use the cleanest, most representative few seconds of your voice."""
    import subprocess
    from pathlib import Path

    from .utils.ffmpeg import ffmpeg_path
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_path(), "-y", "-v", "error", "-ss", str(start), "-t", str(seconds),
         "-i", source, "-af", "loudnorm=I=-19:TP=-2:LRA=11", "-ar", "24000",
         "-ac", "1", out], check=True)
    typer.echo(f"Wrote {out}. Set voice.yaml -> provider: f5tts to use your clone.")


@app.command()
def brand():
    """(Re)generate channel brand assets — logo + banner — into branding/, using
    channel.name + branding.accent_color from config."""
    from pathlib import Path
    from .brand_assets import make_banner, make_logo
    from .config import channel_config
    cfg = channel_config()
    name = cfg["channel"]["name"]
    accent = cfg["branding"]["accent_color"]
    Path("branding").mkdir(exist_ok=True)
    make_logo(name, accent, Path("branding/logo.png"))
    # Use a cached trailer frame as backdrop if available.
    bg = next(iter(Path("assets_cache").glob("trailer_*.mp4")), None)
    bgpng = None
    if bg:
        import subprocess
        from .utils.ffmpeg import ffmpeg_path
        bgpng = "branding/_bg.png"
        subprocess.run([ffmpeg_path(), "-y", "-v", "error", "-ss", "10", "-i", str(bg),
                        "-frames:v", "1", bgpng], check=False)
    make_banner(name, accent, Path("branding/banner.png"), backdrop=bgpng)
    typer.echo(f"Brand assets for '{name}' -> branding/logo.png + branding/banner.png")


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
def history(game: str = typer.Option(None, help="Nexus game domain (default: configured game)")):
    """Show videos already made (so they're never repeated). The 'no repeats' rule
    excludes these mods from future automated selections."""
    import os
    if game:
        os.environ["MODREVIEWER_GAME"] = game
    from .config import channel_config
    from .history import _load
    g = game or channel_config()["channel"]["game_domain"]
    entries = _load().get(g, [])
    if not entries:
        typer.echo(f"No videos recorded yet for '{g}'.")
        return
    typer.echo(f"{len(entries)} video(s) recorded for '{g}':")
    for e in entries:
        typer.echo(f"  {e.get('date','')}  {e.get('title','')}  "
                   f"({len(e.get('mod_ids', []))} mods)")


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
def autospec(
    category: str = typer.Argument(..., help="Category id (e.g. magic, gameplay, weapons)"),
    count: int = typer.Option(12, help="How many mods (≥12 keeps the video over 8 min)"),
    part: int = typer.Option(None, help="Mark as a 'Part N' follow-up video"),
    out: str = typer.Option(None, help="Output spec path (default examples/<slug>.yaml)"),
    game: str = typer.Option(None, help="Nexus game domain (default: configured game)"),
    no_gallery: bool = typer.Option(False, help="Skip gallery scrape (1 image per mod)"),
):
    """Auto-generate a full, render-ready script spec for a category: discovers fresh
    top mods (no repeats), bakes in image galleries, and writes templated countdown
    narration sized for an 8+ minute video. Then: `make <category> --script <out>`."""
    if game:
        import os
        os.environ["MODREVIEWER_GAME"] = game
    from .scripting.autospec import write_autospec
    path = write_autospec(category, out=out, count=count, part=part,
                          with_gallery=not no_gallery)
    typer.echo(f"Wrote {path}\n  Render it:  skyrim-reviewer make {category} "
               f"--script {path} --voice kaggle")


@app.command()
def volume(
    category: str = typer.Argument("new_lands", help="Series category (default new_lands)"),
    count: int = typer.Option(16, help="Mods per volume"),
    vol: int = typer.Option(None, help="Volume number (default: next in the series)"),
    render: bool = typer.Option(True, help="Render+publish now (else just write the spec)"),
    voice: str = typer.Option("kaggle", help="TTS provider for the render"),
    game: str = typer.Option(None, help="Nexus game domain (default: configured game)"),
):
    """Produce the next VOLUME of a numbered series (e.g. the New Lands & Quest 'Vol. N'
    run). Auto-picks the next volume number, pulls fresh mods (no repeats, paging deep
    into the catalogue), titles it 'Vol. N', then renders + publishes."""
    if game:
        import os
        os.environ["MODREVIEWER_GAME"] = game
    from .scripting.autospec import autospec, next_volume
    from .scripting.manual import write_spec
    n = vol or next_volume(category)
    typer.echo(f"Building {category} Vol. {n} ({count} fresh mods)...")
    spec = autospec(category, count=count, part=n)
    spec["slug"] = f"{__import__('datetime').date.today().isoformat()}-{category}-vol{n}"
    path = f"examples/{spec['slug']}.yaml"
    write_spec(spec, path)
    typer.echo(f"  Title:  {spec['title']}")
    typer.echo(f"  Spec:   {path}")
    if not render:
        typer.echo(f"  Render later:  skyrim-reviewer make {category} --script {path} --voice {voice}")
        return
    from .pipeline import run
    p = run(category, profile_name="standard", fmt="category_list",
            script_spec=path, publish=True, voice_override=voice)
    typer.echo(f"  Done -> {p.output_path}\n  GoFile -> {p.gofile_url}")


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
    voice: str = typer.Option(None, help="Override the TTS provider for this run "
                              "(e.g. prerecorded to use GPU-made audio in work/narration)"),
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
        publish=publish, voice_override=voice)


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
