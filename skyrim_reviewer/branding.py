"""Channel-style titles, thumbnail text, and descriptions.

Models the conventions of top Skyrim-mod channels (Heavy Burns / Syn Gaming /
SoftGaming): ALL-CAPS power words, a year, a number, and a punchy thumbnail headline
with a single accent keyword. Style only — content is our own.
"""
from __future__ import annotations

import re
from datetime import date

POWER_WORDS = ["BEST", "INSANE", "ULTIMATE", "ESSENTIAL", "GAME-CHANGING", "MUST-HAVE"]


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


def thumbnail_text(title: str, category_title: str) -> tuple[str, str, str]:
    """Return (headline, accent_keyword, top_banner) for the thumbnail.

    Headline is kept to ~3 punchy words so it's legible at small sizes.
    """
    noun = _short_noun(category_title).upper()
    # A power word: reuse one already in the title if present, else default to BEST.
    kw = next((w for w in POWER_WORDS if w.split("-")[0] in title.upper()), "BEST")
    headline = f"{kw} {noun} MODS" if noun and noun != "SKYRIM" else f"{kw} SKYRIM MODS"
    # Banner: a year mentioned in the title, otherwise the current year.
    m = re.search(r"\b(20\d{2})\b", title)
    banner = m.group(1) if m else str(date.today().year)
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


def thumbnail_variants_text(category_title: str, limit: int = 3) -> list[tuple]:
    """A/B thumbnail (headline, accent_keyword, banner) options."""
    noun = _short_noun(category_title).upper()
    year = str(date.today().year)
    kws = ["BEST", "INSANE", "ULTIMATE", "ESSENTIAL"]
    banners = [year, "MUST-HAVE", "RANKED", "TOP TIER"]
    out = []
    for i in range(limit):
        kw = kws[i % len(kws)]
        head = f"{kw} {noun} MODS" if noun and noun != "SKYRIM" else f"{kw} SKYRIM MODS"
        out.append((head, kw, banners[i % len(banners)]))
    return out


def make_description(project, music_credit: str | None = None,
                     watermark: str = "", next_topic: str = "") -> str:
    """Build a channel-style YouTube description: hook, timestamps, mod links with
    credit, CTA, music attribution, and hashtags."""
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

    if getattr(script, "chapters", None):
        lines.append("⏱ Timestamps")
        lines += script.chapters
        lines.append("")

    # Mods featured — always credit authors + link the mod page (NexusMods terms).
    mods = [m for m in project.mods if getattr(m, "page_url", "")]
    if mods:
        lines.append("🔧 Mods featured (support the authors — endorse & download):")
        for m in mods:
            author = getattr(m, "uploaded_by", "") or getattr(m, "author", "") or "Unknown"
            lines.append(f"• {m.name} by {author} — {m.page_url}")
        lines.append("")

    cta = "▶ Subscribe for new Skyrim mod videos twice a week."
    if next_topic:
        cta += f" Next up: {next_topic}."
    lines.append(cta)
    lines.append("")

    if music_credit:
        lines += ["🎵 Music", music_credit, ""]

    noun = category_noun(getattr(project, "category_id", "") or "").lower()
    tags = ["#skyrim", "#skyrimmods", "#skyrimspecialedition", "#bethesda",
            "#pcgaming", "#moddedskyrim"]
    lines.append(" ".join(tags))
    if watermark:
        lines.append(watermark)
    return "\n".join(lines).strip()
