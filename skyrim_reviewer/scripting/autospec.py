"""Auto-generate a full, render-ready script spec from a category.

Hand-writing a 12-mod narration per video does not scale. This builds the whole
spec automatically from live data:

  1. discover_mods() pulls the top mods for a category from the v2 GraphQL catalog,
     sorted by endorsements, and drops anything already in history.json (no repeats).
  2. For each mod we fetch its image gallery (full screenshots) and bake the URLs
     straight into the spec, so the render downloads them with no extra scrape step.
  3. Narration is templated from each mod's real summary plus rotating, category-aware
     value sentences — a countdown from N to 1 — sized to clear the ≥8-minute bar.

The output is the same YAML spec the manual path consumes, so it flows through the
existing pipeline (assets -> Kaggle F5 voice -> ffmpeg -> publish) unchanged. Tune
or rewrite any line by hand afterwards — it's just a spec file.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..models import Mod

# Spoken ordinals for the countdown ("Number twelve", ... "number one").
_ORD = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
    8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
    14: "fourteen", 15: "fifteen",
}

# Lead-ins so consecutive entries don't all start "Number N:".
_LEADS = ["Number {o}:", "At number {o}:", "Coming in at number {o}:",
          "Next up, number {o}:", "Number {o} on the list:", "Then at number {o}:"]

# Category-specific flavour: hook line, what the video is "about", and a pool of
# value sentences rotated through the entries to add variety and pad to length.
_FLAVOUR = {
    "magic": {
        "title": "Best Skyrim Magic & Spell Mods",
        "noun": "magic mods",
        "subject": "spellcasting",
        "values": [
            "If you've ever felt like vanilla magic runs out of steam by mid-game, this is exactly the kind of mod that fixes it.",
            "It's the sort of thing that makes a pure mage run feel viable from level one all the way to the end.",
            "The spell effects are gorgeous too, so your screen actually looks like you're casting real, dangerous magic.",
            "It slots cleanly alongside the other mods on this list, so you can stack them into one cohesive overhaul.",
            "For anyone who's only ever played a stealth archer, this is the mod that finally makes magic tempting.",
            "It's lightweight, lore-friendly, and balanced, which is rarer than it should be in magic mods.",
        ],
    },
    "gameplay": {
        "title": "Best Skyrim Gameplay Overhaul Mods",
        "noun": "gameplay mods",
        "subject": "how Skyrim actually plays",
        "values": [
            "It's one of those changes you won't be able to play without once you've felt the difference.",
            "It fixes something the base game got wrong in a way that feels completely natural, never intrusive.",
            "It works beautifully with the other picks here, so together they basically rebuild the moment-to-moment experience.",
            "If your last playthrough started to feel stale, this is the mod that makes the world feel alive again.",
            "It's the kind of deep, systemic improvement that you stop noticing precisely because it just feels right.",
            "Lightweight, stable, and endlessly compatible, it's an easy recommendation for any load order.",
        ],
    },
    "new_lands": {
        "title": "Best Skyrim New Lands & Quest Mods",
        "noun": "new lands mods",
        "subject": "exploration",
        "values": [
            "It's the kind of adventure that makes Skyrim feel enormous all over again.",
            "Whole new places to explore means dozens of fresh hours added to your playthrough.",
            "The world-building and atmosphere here genuinely rival the base game's best moments.",
            "If you've explored every inch of vanilla Skyrim, this is exactly the fix you need.",
            "It drops in seamlessly, so you can stumble into the adventure right in your current save.",
            "For anyone who plays Skyrim for the journey and the discovery, this is essential.",
        ],
    },
    "weapons": {
        "title": "Best Skyrim Weapon Mods",
        "noun": "weapon mods",
        "subject": "your arsenal",
        "values": [
            "Every blade is lore-friendly and properly balanced, so nothing here feels like cheating.",
            "The craftsmanship on the models and textures is genuinely on par with official content.",
            "It folds right into the world's leveled lists, so you'll find these naturally as you explore.",
            "Whether you're a sword-and-board warrior or a sneaky assassin, there's something here calling your name.",
            "Paired with the other mods on this list, it turns loot into something you actually get excited about again.",
            "It's a must-have for anyone who's tired of swinging the same handful of vanilla weapons for the hundredth time.",
        ],
    },
}

_GENERIC_VALUES = [
    "It's the kind of mod that quietly makes everything around it better.",
    "It's free, it's polished, and it slots neatly into almost any load order.",
    "Combined with the other picks on this list, it adds up to a dramatically better Skyrim.",
    "If you somehow haven't tried it yet, consider this your sign to fix that.",
    "It's stable, well-supported, and beloved for good reason.",
    "This is one of those installs you'll keep in every single playthrough.",
]

_BBCODE = re.compile(r"\[/?[a-zA-Z][^\]]*\]")
_URL = re.compile(r"https?://\S+")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    """Strip BBCode/URLs/markup noise from a Nexus summary and tidy whitespace."""
    t = _BBCODE.sub("", text or "")
    t = _URL.sub("", t)
    t = t.replace("\r", " ").replace("\n", " ")
    t = re.sub(r"[!?]{2,}", "!", t)                 # "FLY!!!" -> "FLY!"
    t = re.sub(r"\.{2,}", ".", t)                   # collapse ellipses
    t = re.sub(r"([!?.])\.", r"\1", t)              # "FLY!." -> "FLY!"
    t = re.sub(r"([.!?])([A-Z])", r"\1 \2", t)      # "beautiful.There" -> ". There"
    t = _WS.sub(" ", t).strip()
    return t


def _sentences(text: str, n: int = 2) -> str:
    """Return the first n *complete* sentences of cleaned text.

    Nexus summaries are themselves often truncated mid-sentence, so we keep only
    sentences that actually end on terminal punctuation — never invent an ending that
    leaves a dangling fragment like "the arcane arts have now."
    """
    t = _clean(text)
    # Sentences that end on ./!/? (the regex requires the terminator be present).
    complete = re.findall(r".+?[.!?](?=\s|$)", t)
    out = " ".join(s.strip() for s in complete[:n]).strip()
    if not out:                                     # no full sentence -> take the lead
        out = t[:160].rsplit(" ", 1)[0].strip()
        if out and out[-1] not in ".!?":
            out += "."
    return out


def _spoken_name(name: str) -> str:
    """A cleaner, speakable form of a mod title (drop edition tags / parentheticals)."""
    n = re.sub(r"\([^)]*\)", "", name or "").strip()      # drop "(Converted for SSE)"
    n = re.sub(r"\s*[-–]\s*(SSE|SE|AE|LE|Special Edition)\b.*$", "", n, flags=re.I)
    n = re.sub(r"\b(SSE|SE|AE|LE)\b\s*$", "", n).strip()
    n = re.sub(r"\s{2,}", " ", n).strip(" -–")
    return n or (name or "").strip()


def _clean_author(name: str) -> str:
    """Tidy author display names (drop 'Deleted…User' tombstones and noise)."""
    name = (name or "").strip()
    if not name or re.fullmatch(r"Deleted\d+User", name) or name.lower() == "deleted":
        return "the author"
    return name


def _mod_narration(mod: Mod, rank: int, idx: int, flavour: dict, total: int) -> str:
    lead = _LEADS[idx % len(_LEADS)].format(o=_ORD.get(rank, str(rank)))
    author = _clean_author(mod.uploaded_by or mod.author)
    desc = _sentences(mod.summary, 4)
    values = flavour.get("values", _GENERIC_VALUES)
    # Three distinct value beats per entry (offset so neighbours don't echo). The F5
    # voice narrates at ~176 wpm, so each mod needs ~90+ words to keep a 13-15 mod
    # countdown comfortably over the 8-minute video target.
    v1 = values[idx % len(values)]
    v2 = _GENERIC_VALUES[(idx + 2) % len(_GENERIC_VALUES)]
    v3 = values[(idx + 3) % len(values)]
    endo = getattr(mod, "endorsements", 0) or 0
    social = (f" With well over {endo // 1000} thousand endorsements, the community "
              f"clearly agrees this one's special." if endo >= 2000 else "")
    name = _spoken_name(mod.name)
    if rank == 1:
        return _WS.sub(" ", (
            f"And finally, the number one pick on the whole list: {name} by {author}. "
            + (desc + " " if desc else "")
            + v1 + " " + v2 + " " + v3 + social
            + " Honestly, if you only install one mod from this entire video, make it "
            f"this one — it's the perfect note to end on.")).strip()
    body = f"{lead} {name} by {author}. "
    if desc:
        body += desc + " "
    body += v1 + " " + v2 + " " + v3 + social
    return _WS.sub(" ", body).strip()


def build_spec(category: str, mods: list[Mod], *, part: int | None = None,
               flavour: dict | None = None,
               galleries: dict[int, list[str]] | None = None) -> dict:
    """Assemble a full script spec (hook/intro/countdown/outro) from ranked mods."""
    galleries = galleries or {}
    fl = flavour or _FLAVOUR.get(category, {})
    title_base = fl.get("title", f"Best Skyrim {category.title()} Mods")
    noun = fl.get("noun", f"{category} mods")
    n = len(mods)
    year = date.today().year

    if part and part > 1:
        title = f"{n} MORE Skyrim {noun.replace(' mods','').title()} Mods You NEED! (Part {part})"
        hook = (f"We're back — and this time it's part {part}. You loved the last "
                f"round so much that I went digging for {n} more of the very best "
                f"{noun} Skyrim has to offer, and honestly, some of these might be "
                f"even better than before. Every single one is free, every author is "
                f"linked below, and the number one pick is an absolute must-have. "
                f"Let's get straight into it.")
    else:
        title = f"These {n} Skyrim {noun.replace(' mods','').title()} Mods Are INSANE! ({year})"
        hook = (f"Skyrim is over a decade old, but thanks to its modding community it "
                f"has never looked or played better — especially when it comes to "
                f"{noun}. Today I'm counting down {n} of the absolute best {noun} you "
                f"can install right now, all of them free, all of them linked down "
                f"below. Stick around to the end, because the number one pick is the "
                f"one I genuinely couldn't play without. Let's jump in.")

    intro = (f"Quick note before we start: everything here is completely free on "
             f"Nexus Mods, and every creator is credited in the description, so please "
             f"go endorse their work — it's the least we can do for this much free "
             f"content. We're counting down from number {_ORD.get(n, str(n))} all the "
             f"way to number one, so settle in. Here we go.")

    outro = (f"And that's the list — {n} of the best {noun} in {year}. Every mod is "
             f"linked below with full credit to the brilliant authors who made them, "
             f"so go show them some love. If this helped you out, subscribe, because I "
             f"put out two new Skyrim modding videos every single week. Thanks so much "
             f"for watching, and I'll see you in the next one.")

    segments = [
        {"kind": "hook", "narration": hook},
        {"kind": "intro", "narration": intro},
    ]
    spec_mods = []
    for idx, mod in enumerate(mods):
        rank = n - idx                       # countdown: first shown is number n
        segments.append({
            "kind": "mod", "ref": idx + 1,
            "narration": _mod_narration(mod, rank, idx, fl, n),
        })
        urls = []
        if getattr(mod, "picture_url", ""):
            urls.append(mod.picture_url)
        for u in galleries.get(mod.mod_id, []) or []:
            if u not in urls:
                urls.append(u)
        m = {
            "mod_id": mod.mod_id,
            "name": mod.name,
            "author": mod.uploaded_by or mod.author,
            "endorsements": mod.endorsements,
            "summary": _clean(mod.summary)[:600],
            "page_url": mod.page_url,
            "media_ok": True,
        }
        if urls:
            m["image_url"] = urls[0]
            if len(urls) > 1:
                m["image_urls"] = urls[1:6]
        spec_mods.append(m)
    segments.append({"kind": "outro", "narration": outro})

    slug = f"{date.today().isoformat()}-{category}"
    if part:
        slug += f"-pt{part}"
    return {
        "slug": slug,
        "title": title,
        "category_id": category,
        "format": "category_list",
        "hook_line": title_base.replace("Best Skyrim ", "Best "),
        "description": (f"{title}\n\nThe very best {noun} you can play in {year}, "
                        f"counted down from {n} to 1. Every mod is linked below with "
                        f"full credit to its author — go endorse them!"),
        "tags": ["skyrim", "skyrim mods", category, "best skyrim mods", str(year)],
        "segments": segments,
        "mods": spec_mods,
    }


# High-endorsement entries that are NOT showcase-worthy in a "best of" countdown:
# translations, patches, trackers, markers — they pad the top of the list but make
# for weak video segments. Matched case-insensitively against the mod name.
_JUNK = re.compile(
    r"\b(translation|delayed start|alternate routes?|bugfix|hotfix|"
    r"completion tracker|quest markers?|patch|cleaned|tweak|unofficial|"
    r"add-?on)\b", re.I)


def _is_showcase(mod: Mod) -> bool:
    return not _JUNK.search(mod.name or "")


def autospec(category: str, count: int = 12, *, domain: str | None = None,
             part: int | None = None, with_gallery: bool = True,
             exclude_ids: set[int] | None = None) -> dict:
    """Discover fresh mods for a category and return a render-ready spec dict.

    `exclude_ids` skips additional mods on top of the no-repeat history — useful for
    generating two back-to-back videos (the second excludes the first's picks).
    """
    from ..config import channel_config
    from ..history import seen_mod_ids
    from ..research.gallery import fetch_gallery
    from ..research.graphql import discover_mods, graphql_categories_for

    domain = domain or channel_config()["channel"]["game_domain"]
    names = graphql_categories_for(category)
    if not names:
        raise ValueError(f"No GraphQL categories mapped for '{category}'.")
    seen = set(seen_mod_ids(domain)) | set(exclude_ids or set())
    pool = discover_mods(domain, names, count=max(count * 6, 60))
    fresh = [m for m in pool if m.mod_id not in seen and _is_showcase(m)]
    chosen = fresh[:count]
    if len(chosen) < count:
        raise ValueError(
            f"Only {len(chosen)} fresh '{category}' mods available (wanted {count}).")
    # Endorsement DESC means the first item is the strongest; reverse so the
    # countdown climaxes on the single best mod at number one.
    chosen = list(reversed(chosen))
    galleries: dict[int, list[str]] = {}
    if with_gallery:
        for m in chosen:
            try:
                galleries[m.mod_id] = fetch_gallery(m.mod_id, domain, max_images=6)
            except Exception:
                galleries[m.mod_id] = []
    return build_spec(category, chosen, part=part, galleries=galleries)


def write_autospec(category: str, out: str | Path | None = None, **kw) -> str:
    """Generate + write a spec YAML; returns the path."""
    from .manual import write_spec
    spec = autospec(category, **kw)
    out = Path(out) if out else Path("examples") / f"{spec['slug']}.yaml"
    write_spec(spec, out)
    return str(out)
