"""Manual / chat-authored script path — no Anthropic API key required.

When you (or the assistant, here in the chat) write the script by hand, drop it
into a YAML spec and the pipeline ingests it instead of calling the Claude API.
The spec can also embed the mods inline, so the whole pipeline runs with NO API
keys at all (research + scripting done in chat; only a voice is needed).

Spec format (see examples/ for a full one):

    title: "I Turned Skyrim Into The Witcher"
    hook_line: "Skyrim Is Now The Witcher"
    format: transformation
    theme: "The Witcher"
    description: "..."
    tags: [witcher, skyrim, mods]
    next_topic: "Transforming Skyrim into Elden Ring"
    mods:
      - name: "Witcher-style Combat"
        author: "SomeAuthor"
        page_url: "https://www.nexusmods.com/skyrimspecialedition/mods/123"
        image_url: ""          # optional; only if you have permission
        media_ok: false        # permission to show this mod's media
    segments:
      - kind: hook
        title: "Cold open"
        narration: "..."
        target_seconds: 12
      - kind: mod
        ref: 1                 # 1-based index into mods (or use mod_id:)
        title: "Combat"
        narration: "..."
        target_seconds: 75
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..models import MediaAsset, Mod, Project, Script, Segment, VideoFormat


def spec_skeleton(mods, *, title: str, fmt: str, profile, next_topic: str = "",
                  theme: str = "") -> dict:
    """Build a script-spec skeleton from researched mods, with EMPTY narration.

    The mods (and their permission flags) come from live research; the narration is
    left blank for a human/assistant to write in chat. Saves the API-research ->
    chat-authored-script bridge when you have a Nexus key but no Anthropic key.
    """
    segs = [
        {"kind": "hook", "title": "Cold open", "target_seconds": profile.hook_seconds,
         "narration": ""},
        {"kind": "intro", "title": "The promise", "target_seconds": profile.intro_seconds,
         "narration": ""},
    ]
    for i, m in enumerate(mods, 1):
        segs.append({"kind": "mod", "ref": i, "title": m.name,
                     "target_seconds": profile.seconds_per_mod, "narration": ""})
    segs.append({"kind": "outro", "title": "Outro",
                 "target_seconds": profile.outro_seconds, "narration": ""})
    spec = {
        "title": title,
        "hook_line": "",
        "format": fmt,
        "next_topic": next_topic,
        "tags": [],
        "description": "",
        "mods": [{
            "mod_id": m.mod_id, "name": m.name, "author": m.uploaded_by or m.author,
            "page_url": m.page_url, "summary": m.summary,
            "image_url": m.picture_url, "media_ok": m.allow_media_reuse,
        } for m in mods],
        "segments": segs,
    }
    if theme:
        spec["theme"] = theme
    return spec


def write_spec(spec: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(spec, fh, sort_keys=False, allow_unicode=True, width=100)


def load_spec(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def apply_spec(project: Project, spec: dict) -> Project:
    """Populate project.mods and project.script from a hand-written spec."""
    # Optional slug override so multiple videos of the same category/day don't collide
    # (output + workdir are keyed off the slug).
    if spec.get("slug"):
        from pathlib import Path as _P
        project.slug = str(spec["slug"])
        project.workdir = str(_P("work") / project.slug)
        _P(project.workdir).mkdir(parents=True, exist_ok=True)
    # --- mods (embedded inline; no Nexus call needed) ---
    mods: list[Mod] = []
    for i, m in enumerate(spec.get("mods", []), 1):
        mod = Mod(
            mod_id=int(m.get("mod_id", i)),
            name=m.get("name", f"Mod {i}"),
            author=m.get("author", ""),
            uploaded_by=m.get("author", ""),
            summary=m.get("summary", ""),
            endorsements=int(m.get("endorsements", 0)),
            page_url=m.get("page_url", ""),
            allow_media_reuse=bool(m.get("media_ok", False)),
        )
        # Accept a single image_url and/or a list of image_urls (more images = more
        # variety per mod). Order preserved, duplicates dropped.
        urls = []
        if m.get("image_url"):
            urls.append(m["image_url"])
        urls.extend(m.get("image_urls", []) or [])
        for u in dict.fromkeys(urls):
            mod.media.append(MediaAsset(url=u, kind="image"))
        mods.append(mod)
    project.mods = mods

    # index mods for ref resolution (1-based) and by mod_id
    by_index = {i: mod for i, mod in enumerate(mods, 1)}
    by_id = {mod.mod_id: mod for mod in mods}

    # --- segments ---
    segments: list[Segment] = []
    counters = {"hook": 0, "intro": 0, "mod": 0, "outro": 0}
    for s in spec.get("segments", []):
        kind = s["kind"]
        counters[kind] = counters.get(kind, 0) + 1
        seg_id = s.get("segment_id") or (
            kind if kind in {"hook", "intro", "outro"} else f"mod_{counters['mod']:02d}")
        mod_id = None
        if "mod_id" in s:
            mod_id = int(s["mod_id"])
        elif "ref" in s:
            ref = by_index.get(int(s["ref"]))
            mod_id = ref.mod_id if ref else None
        segments.append(Segment(
            segment_id=seg_id,
            kind=kind,
            title=s.get("title", ""),
            narration=s.get("narration", "").strip(),
            target_seconds=float(s.get("target_seconds", 0)),
            mod_id=mod_id,
        ))

    fmt = VideoFormat(spec.get("format", project.format.value))
    credits = "\n".join(f"• {m.credit_line()}" for m in mods)
    description = (spec.get("description", "").strip()
                  + ("\n\nMods featured (full credit to their authors):\n" + credits
                     if mods else ""))
    project.script = Script(
        title=spec["title"],
        format=fmt,
        hook_line=spec.get("hook_line", ""),
        description=description,
        tags=spec.get("tags", []),
        chapters=[seg.title for seg in segments],
        segments=segments,
    )
    project.format = fmt
    if spec.get("theme"):
        project.theme = spec["theme"]
    return project
