"""Viral video-idea generator.

Models the proven formats of popular Skyrim-mod channels (config/reference_channels.yaml
— Heavy Burns, Brodual, MxR, Mern, etc.) and crosses them with this channel's
category buckets to propose ready-to-produce video ideas: a clickable title, the hook,
the pipeline format to use, the inspiring channels, and the exact `make` command.

Offline by default. Pass live=True to attach real currently-trending mods (one API
call per idea) and, when FIRECRAWL_API_KEY is set, a sample of what the idea's
inspiring reference channel(s) are currently publishing (research/reference_scrape.py).
"""
from __future__ import annotations

import random
from datetime import date

from .config import channel_config, load_yaml


def _category_noun(title: str) -> str:
    """'Best Skyrim Weapon Mods' -> 'Weapon'; 'Best Skyrim Graphics & Visual Mods' -> 'Graphics & Visual'."""
    return (title.replace("Best Skyrim", "").replace("Mods", "")
            .replace("&", "&").strip()) or "Mod"


def generate_ideas(n: int = 8, live: bool = False, seed: int | None = None) -> list[dict]:
    rng = random.Random(seed)
    ref = load_yaml("reference_channels.yaml")
    cats = channel_config()["categories"]
    year = date.today().year

    # Build the full space of (format x category) combinations, then sample a diverse set.
    combos = []
    for fmt in ref["formats"]:
        if fmt["id"] in ("new_year",):          # category-agnostic formats
            combos.append((fmt, None))
        elif fmt["id"] == "transformation":
            for theme in ref["themes"]:
                combos.append((fmt, {"theme": theme}))
        else:
            for cat in cats:
                combos.append((fmt, cat))
    # Weighted shuffle: categories the channel's own analytics say perform get
    # sampled first (Efraimidis–Spirakis; weight 1.0 when `learn` has never run).
    from .analytics import load_insights
    cat_w = load_insights().get("category_weights") or {}

    def _weight(combo) -> float:
        _, ctx = combo
        return cat_w.get((ctx or {}).get("id", ""), 1.0)

    combos.sort(key=lambda c: rng.random() ** (1.0 / max(_weight(c), 0.01)),
                reverse=True)

    ideas, seen_titles, used_formats = [], set(), {}
    for fmt, ctx in combos:
        if len(ideas) >= n:
            break
        # Encourage variety: don't let one format dominate.
        if used_formats.get(fmt["id"], 0) >= max(1, n // 3):
            continue

        cat = ctx if (ctx and "id" in (ctx or {})) else None
        noun = _category_noun(cat["title"]) if cat else "Mod"
        fields = {
            "n": rng.choice([5, 7, 10]),
            "superlative": rng.choice(ref["superlatives"]),
            "category_noun": noun,
            "year": year,
            "theme": (ctx or {}).get("theme", "The Witcher"),
        }
        title = fmt["template"].format(**fields)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        used_formats[fmt["id"]] = used_formats.get(fmt["id"], 0) + 1

        cmd = f"skyrim-reviewer make {cat['id'] if cat else 'trending'} --fmt {fmt['pipeline_fmt']}"
        if fmt["id"] == "transformation":
            cmd += f' --theme "{fields["theme"]}"'

        idea = {
            "title": title,
            "hook": fmt["hook"].format(**fields),
            "format": fmt["id"],
            "pipeline_fmt": fmt["pipeline_fmt"],
            "inspired_by": fmt.get("inspired_by", []),
            "category": cat["id"] if cat else "trending",
            "command": cmd,
            "mods": [],
            "live_reference_titles": [],
        }
        if live and cat:
            try:
                from .research import research_category
                mods = research_category(cat["id"], fields["n"])
                idea["mods"] = [m.name for m in mods[:fields["n"]]]
            except Exception:
                pass
        if live and fmt.get("inspired_by"):
            from .research.reference_scrape import live_channel_titles
            channel = rng.choice(fmt["inspired_by"])
            idea["live_reference_titles"] = live_channel_titles(channel, limit=3)
        ideas.append(idea)
    return ideas
