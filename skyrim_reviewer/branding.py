"""Channel-style titles, thumbnail text, and descriptions.

Models the conventions of top Skyrim-mod channels (Heavy Burns / Syn Gaming /
SoftGaming): ALL-CAPS power words, a year, a number, and a punchy thumbnail headline
with a single accent keyword. Style only — content is our own.
"""
from __future__ import annotations

import re
from datetime import date

POWER_WORDS = ["BEST", "INSANE", "ULTIMATE", "ESSENTIAL", "GAME-CHANGING", "MUST-HAVE"]

# Clean, short thumbnail nouns keyed by category id (reliable — the video TITLE is too
# messy to parse a noun out of, e.g. "These 15 Skyrim Magic Mods Are INSANE!").
CATEGORY_NOUNS = {
    "weapons": "WEAPON", "armor": "ARMOR", "new_lands": "NEW LANDS",
    "graphics": "GRAPHICS", "gameplay": "GAMEPLAY", "magic": "MAGIC",
    "followers": "FOLLOWER", "combat": "COMBAT", "quests": "QUEST",
}

# A scroll-stopping accent keyword per category (less generic than always "BEST").
CATEGORY_HOOKS = {
    "magic": "GOD-TIER", "weapons": "DEADLY", "gameplay": "GAME-CHANGING",
    "graphics": "NEXT-GEN", "new_lands": "EPIC", "armor": "LEGENDARY",
    "followers": "BEST", "quests": "EPIC",
}


def noun_for_category(category_id: str, fallback_title: str = "") -> str:
    """Clean thumbnail noun from the category id, falling back to title parsing."""
    if category_id in CATEGORY_NOUNS:
        return CATEGORY_NOUNS[category_id]
    return _short_noun(fallback_title).upper()


def category_noun(category_title: str) -> str:
    """'Best Skyrim Weapon Mods' -> 'Weapon'."""
    return (category_title.replace("Best Skyrim", "").replace("Mods", "").strip()
            or "Skyrim")


def _short_noun(category_title: str) -> str:
    """A short noun for thumbnails (drop '& ...' and extra words) so the big headline
    fits without chopping. 'New Lands & Quest' -> 'New Lands'; 'Graphics & Visual' ->
    'Graphics'."""
    noun = category_noun(category_title).split("&")[0].strip()
    words = noun.split()
    return " ".join(words[:2]) if words else "Skyrim"


def thumbnail_text(title: str, category_title: str,
                   category_id: str = "") -> tuple[str, str, str]:
    """Return (headline, accent_keyword, top_banner) for the thumbnail.

    Headline is kept to ~3 punchy words so it's legible at small sizes. The noun comes
    from the category id when available (the video title is too messy to parse).
    """
    noun = noun_for_category(category_id, category_title) if category_id \
        else _short_noun(category_title).upper()
    kw = CATEGORY_HOOKS.get(category_id, "BEST")
    headline = f"{kw} {noun} MODS" if noun and noun != "SKYRIM" else f"{kw} SKYRIM MODS"
    # Banner: a year mentioned in the title, otherwise the current year.
    m = re.search(r"\b(20\d{2})\b", title)
    banner = f"SKYRIM • {m.group(1) if m else date.today().year}"
    return headline, kw, banner


def title_variants(category_title: str, n_mods: int, fmt: str = "category_list",
                   limit: int = 3) -> list[str]:
    """A/B title options from the configured channel-style templates."""
    from .config import channel_config
    noun = category_noun(category_title)
    year = date.today().year
    tmpls = channel_config().get("title_templates", {}).get(fmt, [])
    out: list[str] = []
    for t in tmpls:
        try:
            out.append(t.format(n=n_mods, category=noun, year=year, theme="The Witcher"))
        except Exception:
            continue
    seen: list[str] = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen[:limit] or [f"The BEST Skyrim {noun} Mods in {year}!"]


def thumbnail_variants_text(category_title: str, limit: int = 3,
                            category_id: str = "") -> list[tuple]:
    """A/B thumbnail (headline, accent_keyword, banner) options."""
    noun = noun_for_category(category_id, category_title) if category_id \
        else _short_noun(category_title).upper()
    year = str(date.today().year)
    # Lead with the category's signature hook, then strong alternates.
    kws = [CATEGORY_HOOKS.get(category_id, "BEST"), "INSANE", "ULTIMATE", "ESSENTIAL"]
    banners = [f"SKYRIM • {year}", "MUST-HAVE", "RANKED", "TOP TIER"]
    out = []
    for i in range(limit):
        kw = kws[i % len(kws)]
        head = f"{kw} {noun} MODS" if noun and noun != "SKYRIM" else f"{kw} SKYRIM MODS"
        out.append((head, kw, banners[i % len(banners)]))
    return out


# Category-specific search keywords (what people actually type on YouTube).
SEO_KEYWORDS = {
    "new_lands": ["skyrim new lands mods", "skyrim new worldspace", "skyrim dlc mods",
                  "skyrim exploration mods", "skyrim new island", "skyrim expansion mods"],
    "quests": ["skyrim quest mods", "skyrim best quest mods", "skyrim story mods",
               "skyrim questline mods", "skyrim adventure mods", "skyrim dlc sized quest"],
    "magic": ["skyrim magic mods", "skyrim spell mods", "skyrim best spells",
              "skyrim mage build", "skyrim magic overhaul"],
    "weapons": ["skyrim weapon mods", "skyrim best weapons", "skyrim sword mods",
                "skyrim weapon pack"],
    "armor": ["skyrim armor mods", "skyrim armor pack", "skyrim best armor",
              "skyrim clothing mods"],
    "graphics": ["skyrim graphics mods", "skyrim enb", "skyrim 4k textures",
                 "skyrim next gen graphics", "skyrim visual mods"],
    "gameplay": ["skyrim gameplay mods", "skyrim combat mods", "skyrim overhaul mods",
                 "skyrim immersion mods"],
    "followers": ["skyrim follower mods", "skyrim companion mods",
                  "skyrim best followers", "skyrim custom follower"],
}
_HASHTAGS = {
    "new_lands": ["#newlands", "#exploration"], "quests": ["#questmods", "#skyrimquests"],
    "magic": ["#magic", "#spells"],
    "weapons": ["#weapons"], "armor": ["#armor"], "graphics": ["#graphics", "#enb"],
    "gameplay": ["#gameplay"], "followers": ["#followers"],
}


def seo_tags(category_id: str, project=None, limit_chars: int = 480) -> list[str]:
    """A keyword-researched YouTube tag list (deduped, capped to YouTube's ~500-char
    budget): evergreen Skyrim terms + category keywords + a few featured mod names."""
    year = date.today().year
    base = ["skyrim", "skyrim mods", f"skyrim mods {year}", "best skyrim mods",
            "skyrim special edition", "skyrim anniversary edition", "skyrim se mods",
            "skyrim ae mods", "modded skyrim", "skyrim mod list", "skyrim load order",
            "skyrim xbox mods", "skyrim pc mods", "bethesda", "skyrim 2011"]
    tags = SEO_KEYWORDS.get(category_id, []) + base
    if project is not None:
        ranked = sorted(getattr(project, "mods", []),
                        key=lambda m: getattr(m, "endorsements", 0), reverse=True)
        for m in ranked[:5]:
            nm = (getattr(m, "name", "") or "").split(" - ")[0].strip().lower()
            if 3 <= len(nm) <= 30:
                tags.append(nm)
    out, used = [], 0
    for t in dict.fromkeys(tags):                 # dedupe, preserve order
        if used + len(t) + 1 > limit_chars:
            break
        out.append(t)
        used += len(t) + 1
    return out


def pinned_comment(project) -> str:
    """A ready-to-paste pinned comment: every featured mod linked with credit, plus a
    CTA. (Links in the pinned comment drive clicks the description often buries.)"""
    lines = ["🔧 Every mod from the video (go endorse these legends!):", ""]
    mods = [m for m in project.mods if getattr(m, "page_url", "")]
    for m in mods:
        author = getattr(m, "uploaded_by", "") or getattr(m, "author", "") or "Unknown"
        lines.append(f"• {m.name} by {author} — {m.page_url}")
    lines += ["", "👉 Which one's going in YOUR load order? Let me know below!",
              "🔔 Subscribe for new Skyrim mod videos twice a week."]
    return "\n".join(lines)


def mod_list_page(project) -> str:
    """A standalone markdown page listing every featured mod, linked and credited.

    YouTube's 5000-character description can't hold a hundred links, so the full
    list lives as its own page and the description points at it. Grouped by tier
    for ranked_tier_list videos, otherwise in countdown order.
    """
    script = project.script
    mods = {m.mod_id: m for m in project.mods if getattr(m, "page_url", "")}
    lines = [f"# {script.title}", ""]
    if getattr(script, "description", ""):
        lines += [script.description.split("Every mod is linked")[0].strip(), ""]
    lines += ["Every mod below is free on Nexus Mods. Full credit to the authors — "
              "please endorse their work.", ""]

    mod_segs = [s for s in script.segments if getattr(s, "kind", "") == "mod"]
    total = len(mod_segs)

    def row(seg, rank) -> str:
        mod = mods.get(seg.mod_id)
        if not mod:
            return ""
        author = getattr(mod, "uploaded_by", "") or getattr(mod, "author", "") or "Unknown"
        return f"| {rank} | [{mod.name}]({mod.page_url}) | {author} |"

    header = ["| # | Mod | Author |", "|---:|---|---|"]
    tiers = [t for t in dict.fromkeys(
        s.tier for s in mod_segs if getattr(s, "tier", None))]
    if tiers:
        # Best tier first, matching how the board reads on screen.
        for tier in tiers[::-1]:
            lines += [f"## {tier} Tier", ""] + header
            for idx, seg in enumerate(mod_segs):
                if getattr(seg, "tier", None) == tier:
                    lines.append(row(seg, total - idx))
            lines.append("")
    else:
        lines += header
        for idx, seg in enumerate(mod_segs):
            lines.append(row(seg, total - idx))
        lines.append("")

    return "\n".join(ln for ln in lines if ln is not None).strip() + "\n"


def mod_list_url(project) -> str:
    """Public URL of this video's mod-list page, or "" when none is configured."""
    try:
        from .config import channel_config
        base = (channel_config().get("branding", {}) or {}).get("mod_list_base_url", "")
    except Exception:
        base = ""
    return f"{base.rstrip('/')}/{project.slug}.md" if base else ""


def make_description(project, music_credit: str | None = None,
                     watermark: str = "", next_topic: str = "",
                     limit: int = 5000) -> str:
    """Build a channel-style YouTube description: hook, timestamps, mod links with
    credit, CTA, music attribution, and hashtags.

    YouTube hard-caps descriptions at `limit` characters and silently drops the rest,
    which used to cut the author credits off long videos entirely. So a list that
    doesn't fit sheds detail in priority order instead: first the per-chapter mod
    links (the pinned comment carries the full credited list), then the separate
    credits block. Complete timestamps always survive — they're what the chapter UI
    needs, and an incomplete list breaks navigation for every mod below the cut."""
    for link_chapters, credit_block in ((True, True), (True, False),
                                        (False, True), (False, False)):
        out = _compose_description(project, music_credit, watermark, next_topic,
                                   link_chapters, credit_block)
        if len(out) <= limit:
            return out
    return out[:limit].rsplit("\n", 1)[0]


def _compose_description(project, music_credit: str | None, watermark: str,
                         next_topic: str, link_chapters: bool,
                         credit_block: bool) -> str:
    from .edit.captions import CHAPTER_LINK_SEP
    script = project.script
    lines: list[str] = [script.title, ""]
    # Keep only the lead paragraph of any existing description — structured credits /
    # timestamps are appended below, so drop them here to avoid duplication.
    desc = getattr(script, "description", "") or ""
    low = desc.lower()
    cut = min([i for i in (low.find("mods featured"), low.find("full credit"),
                           low.find("timestamps"), low.find("🔧"), low.find("⏱"))
               if i != -1] or [len(desc)])
    desc = desc[:cut].strip()
    if desc:
        lines += [desc, ""]

    chapters = list(getattr(script, "chapters", None) or [])
    if chapters:
        if not link_chapters:
            chapters = [c.split(CHAPTER_LINK_SEP)[0] for c in chapters]
        lines.append("⏱ Timestamps")
        lines += chapters
        lines.append("")

    # Mods featured — always credit authors + link the mod page (NexusMods terms).
    mods = [m for m in project.mods if getattr(m, "page_url", "")]
    if mods and credit_block:
        lines.append("🔧 Mods featured (support the authors — endorse & download):")
        for m in mods:
            author = getattr(m, "uploaded_by", "") or getattr(m, "author", "") or "Unknown"
            lines.append(f"• {m.name} by {author} — {m.page_url}")
        lines.append("")
    elif mods:
        url = mod_list_url(project)
        lines += ([f"🔧 Every mod, linked and credited: {url}", ""] if url else
                  ["🔧 Every mod credited and linked in the pinned comment.", ""])

    cta = "▶ Subscribe for new Skyrim mod videos twice a week."
    if next_topic:
        cta += f" Next up: {next_topic}."
    lines.append(cta)
    lines.append("")

    if music_credit:
        lines += ["🎵 Music", music_credit, ""]

    cid = getattr(project, "category_id", "") or ""
    tags = ["#skyrim", "#skyrimmods", "#skyrimspecialedition", "#bethesda",
            "#pcgaming", "#moddedskyrim"] + _HASHTAGS.get(cid, [])
    lines.append(" ".join(tags))
    if watermark:
        lines.append(watermark)
    return "\n".join(lines).strip()
