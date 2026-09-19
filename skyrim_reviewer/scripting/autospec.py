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

import random
import re
from datetime import date
from pathlib import Path

from ..models import Mod

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]

# Per-mod narration length target. At ~176 wpm, ~120 words x ~16 mods + intro/outro
# lands the video in the channel's 10-15 minute band.
_MIN_WORDS_PER_MOD = 120

# Spoken ordinals for the countdown ("Number twelve", ... "number one").
_ORD = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
    8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
    14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
}

# Lead-ins so consecutive entries don't all start "Number N:".
_LEADS = ["Number {o}:", "At number {o}:", "Coming in at number {o}:",
          "Next up, number {o}:", "Number {o} on the list:", "Then at number {o}:",
          "Sliding in at number {o}:", "Kicking off number {o}:"]

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
        "title": "Best Skyrim New Lands Mods",
        "noun": "new lands mods",
        "subject": "exploration",
        "values": [
            "It's a whole new worldspace to explore that makes Skyrim feel enormous all over again.",
            "Whole new places to explore means dozens of fresh hours added to your playthrough.",
            "The world-building and atmosphere here genuinely rival the base game's best moments.",
            "If you've explored every inch of vanilla Skyrim, this new land is exactly the fix you need.",
            "It drops in seamlessly, so you can sail or wander off to somewhere brand new from your current save.",
            "For anyone who plays Skyrim for the journey and the discovery, this is essential.",
        ],
    },
    "quests": {
        "title": "Best Skyrim Quest Mods",
        "noun": "quest mods",
        "subject": "questing",
        "values": [
            "It's a properly written questline with real choices and consequences, not just a fetch quest.",
            "The voice acting and storytelling here punch well above what you'd expect from a free mod.",
            "It weaves into the world so naturally you'll swear it shipped with the base game.",
            "If the main quest left you wanting more, this scratches exactly that itch.",
            "Hours of fresh story content, all of it lore-friendly and lovingly made.",
            "For anyone who plays Skyrim for the stories, this one belongs in your load order.",
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
    "graphics": {
        "title": "Best Skyrim Graphics & Visual Mods",
        "noun": "graphics mods",
        "subject": "how Skyrim looks",
        "values": [
            "The difference is night and day — screenshots genuinely start looking like concept art.",
            "It's the kind of upgrade you notice every few steps as you explore.",
            "It's surprisingly performance-friendly, so you don't need a monster rig to run it.",
            "It plays nicely with ENB and the other visual mods on this list.",
            "Once you've seen Skyrim like this, going back to vanilla is genuinely painful.",
            "Subtle where it should be subtle, dramatic exactly where it counts.",
        ],
    },
    "armor": {
        "title": "Best Skyrim Armor & Clothing Mods",
        "noun": "armor mods",
        "subject": "your character's look",
        "values": [
            "Every piece is lore-friendly, so nothing here breaks the fantasy.",
            "The textures and meshes are detailed enough to stand toe-to-toe with official content.",
            "It fits naturally into the world through leveled lists, so you'll find it as you play.",
            "Heavy-armor tank or light-footed sneak, there's a look here for your build.",
            "It's fantastic for screenshots and roleplay alike.",
            "It's the kind of gear that makes you want to roll a whole new character.",
        ],
    },
    "followers": {
        "title": "Best Skyrim Follower & Companion Mods",
        "noun": "follower mods",
        "subject": "your companions",
        "values": [
            "Fully voiced and genuinely well-written, this is a companion you'll actually want around.",
            "No more silent, lifeless tagalongs — this one has real personality.",
            "They fit seamlessly into the world and react to what's happening around them.",
            "If you usually adventure solo, this might be the mod that changes your mind.",
            "Great banter, genuinely useful in a fight, and not constantly blocking doorways.",
            "It's the kind of companion that makes the long journeys feel a lot less lonely.",
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

# "Who it's for" lines add a concrete, opinionated recommendation angle per entry —
# the kind of editorial substance YouTube's inauthentic-content policy looks for.
_WHO_FOR = {
    "magic": [
        "If you main a battlemage or you've always wanted a real spellsword fantasy, this is for you.",
        "Honestly, if you've only ever played a stealth archer, this is the mod that'll finally convert you to magic.",
        "Pure-mage players are going to get the most out of this one, but it's strong for any build that touches a spell.",
    ],
    "gameplay": [
        "If your hundredth playthrough is starting to feel like muscle memory, this is the reset button.",
        "This is aimed squarely at players who want Skyrim to feel like a modern RPG, not a 2011 one.",
        "Roleplayers and immersion fans especially are going to love what this does.",
    ],
    "new_lands": [
        "If you've already explored every inch of vanilla Skyrim, this brand-new land is what you're craving.",
        "This one's for the explorers — the players who fast-travel the least and wander the most.",
        "Anyone who lives for that 'what's over the next hill' feeling is going to love this.",
    ],
    "quests": [
        "If you play Skyrim mainly for the stories, this questline is right up your alley.",
        "This is for anyone who finished the main quest wishing there were more like it.",
        "Roleplayers and lore nerds especially are going to get a lot out of this one.",
    ],
    "weapons": [
        "Melee builds will get the most mileage here, but there's something for archers and mages too.",
        "If you're the type who reloads a save just to get better loot, this one's calling your name.",
        "This is for anyone tired of swinging the same five vanilla weapons for the hundredth hour.",
    ],
    "graphics": [
        "If you're building a screenshot-worthy setup, this one is non-negotiable.",
        "Anyone chasing that next-gen look is going to get a ton out of this.",
        "Even on modest hardware, this is worth finding room for in your load order.",
    ],
    "armor": [
        "Roleplayers and fashion-souls types are going to love this one.",
        "If you actually care how your character looks, this is for you.",
        "It's a great pick whether you fight up close, at range, or with magic.",
    ],
    "followers": [
        "If you hate adventuring alone, this is exactly what you've been missing.",
        "Perfect for players who care about story and companionship.",
        "Anyone who found the vanilla followers forgettable will be won over.",
    ],
}
_WHO_FOR_GENERIC = [
    "If that sounds like your kind of thing, you're going to want this in your load order.",
    "It's an easy recommendation for just about any playthrough.",
]

# Hook / intro / outro variants — picked per video so different uploads don't open
# with the exact same script (a key anti-"mass-produced template" signal).
_HOOKS_FIRST = [
    "Skyrim is over a decade old, but thanks to its modding community it has never "
    "looked or played better — especially when it comes to {noun}. Today I'm counting "
    "down {n} of the absolute best {noun} you can install right now, all of them free, "
    "all of them linked below. Stick around to the end, because the number one pick is "
    "the one I genuinely couldn't play without. Let's jump in.",
    "I've spent way too many hours digging through Nexus so you don't have to, and I've "
    "narrowed it down to the {n} best {noun} worth your time in {year}. Every single one "
    "is free, every author is credited below, and trust me — the top of this list is "
    "special. Let's get straight into it.",
    "If your Skyrim is starting to feel a little stale, the {n} {noun} on this list are "
    "the fix. These are the mods I'd reinstall first on any fresh setup — all free, all "
    "linked down below, ranked from good to absolutely essential. Let's count them down.",
]
_HOOKS_PART = [
    "We're back — and this time it's part {part}. You loved the last round so much that "
    "I went digging for {n} more of the very best {noun} Skyrim has to offer, and honestly, "
    "some of these might be even better than before. Every one is free, every author is "
    "linked below, and the number one pick is a must-have. Let's get into it.",
    "You asked for more, so here's part {part}: {n} more of the best {noun} I could find, "
    "with zero repeats from the earlier videos. All free, all credited below. Let's dive "
    "straight back in.",
]
_INTROS = [
    "Quick note before we start: everything here is completely free on Nexus Mods, and "
    "every creator is credited in the description, so please go endorse their work — it's "
    "the least we can do for this much free content. We're counting down from number "
    "{nord} all the way to number one, so settle in. Here we go.",
    "Before we dive in — every mod is free, every author is linked below, and a quick "
    "endorsement on Nexus genuinely helps these creators keep going. Alright, counting "
    "down from {nord} to one. Let's do it.",
    "One thing up front: I'm ranking these from number {nord} down to my personal number "
    "one, and reasonable people will absolutely disagree on the order — let me know yours "
    "in the comments. Everything's free and linked below. Let's get started.",
]
_OUTROS = [
    "And that's the list — {n} of the best {noun} in {year}. Every mod is linked below "
    "with full credit to the brilliant authors who made them, so go show them some love. "
    "If this helped you out, subscribe, because I put out two new Skyrim videos every "
    "single week. Thanks so much for watching, and I'll see you in the next one.",
    "So there you go — {n} {noun} that'll seriously transform your game, all free and all "
    "linked below. Drop a comment with the one you'd have put at number one, hit subscribe "
    "for two new Skyrim videos a week, and I'll catch you in the next one.",
    "That wraps up {n} of my favourite {noun} right now. Go endorse the authors down in "
    "the description — they've earned it — and if you want more lists like this, subscribe; "
    "there's a new one every few days. Thanks for watching, see you next time.",
]


# Title frames — curiosity/opinion-driven and varied, so uploads don't all read
# "N MORE Skyrim X Mods You NEED! (Part N)". {short} is the noun ("New Lands").
_TITLE_FRAMES = {
    "first": [
        "I Tested {n} Skyrim {short} Mods — These Are the Best ({year})",
        "These {n} Skyrim {short} Mods Feel Illegal to Have for Free",
        "{n} Skyrim {short} Mods That Completely Changed My Game ({year})",
        "Skyrim {short} Mods Are Out of Control — My Top {n} for {year}",
        "{n} {short} Mods Every Skyrim Player Should Try at Least Once",
    ],
    "part": [
        "I Found {n} MORE Hidden Skyrim {short} Mods ({year})",
        "{n} Skyrim {short} Mods You Probably Missed (Vol. {part})",
        "Even MORE Insane Skyrim {short} Mods — My Top {n} (Part {part})",
        "{n} More Skyrim {short} Mods That Feel Like Free DLC",
        "The Skyrim {short} Mods Nobody Talks About — {n} Gems (Part {part})",
    ],
}
_TITLE_CAT = {
    "new_lands": {
        "first": [
            "Skyrim Has Secret Continents — {n} New Lands Mods Worth Playing",
            "{n} Skyrim Quest Mods That Feel Like Official Expansions ({year})",
        ],
        "part": [
            "{n} More Skyrim Adventures That Feel Like Full DLC (Part {part})",
            "I Played {n} More Skyrim New Lands Mods So You Don't Have To",
            "{n} Skyrim Quest Mods Hiding in Plain Sight (Vol. {part})",
        ],
    },
    "magic": {
        "first": ["{n} Skyrim Magic Mods That Make You Feel Like a God ({year})"],
        "part": ["{n} More Skyrim Magic Mods That Break the Game (Part {part})"],
    },
    "weapons": {
        "first": ["{n} Skyrim Weapon Mods That Make Combat Actually Fun ({year})"],
        "part": ["{n} More Skyrim Weapon Mods Worth Re-rolling For (Part {part})"],
    },
}


# Canonical sequel title — the consistent "Vol. N" branding for a numbered series.
_SERIES_TITLE = "{n} Skyrim {short} Mods You Probably Missed (Vol. {part})"


def _unique_titles(category: str, short: str, n: int, year: int,
                   part: int | None, rng: random.Random) -> list[str]:
    """Return [main_title, alt1, alt2]. Sequels (part>1) lead with the canonical
    'Vol. N' series title for consistent branding, then offer varied alternates."""
    key = "part" if part and part > 1 else "first"
    pool = list(_TITLE_CAT.get(category, {}).get(key, [])) + list(_TITLE_FRAMES[key])
    rng.shuffle(pool)
    out = []
    if key == "part":
        out.append(_SERIES_TITLE.format(n=n, short=short, year=year, part=part))
    for t in pool:
        title = t.format(n=n, short=short, year=year, part=part or 1)
        if title not in out:
            out.append(title)
        if len(out) == 3:
            break
    return out


def _data_facts(mod: Mod) -> list[str]:
    """Real, verifiable stat fragments about a mod (downloads, endorsements, recency,
    age). Only facts we actually have — never invented."""
    facts = []
    dl = getattr(mod, "downloads", 0) or 0
    if dl >= 1_000_000:
        facts.append(f"it's been downloaded over {dl // 1_000_000} million times")
    elif dl >= 100_000:
        facts.append(f"it's pulled in more than {dl // 1000} thousand downloads")
    en = getattr(mod, "endorsements", 0) or 0
    if en >= 2000:
        facts.append(f"more than {en // 1000} thousand players have endorsed it")
    u = getattr(mod, "updated_at", None)
    if u:
        months = (date.today().year - u.year) * 12 + (date.today().month - u.month)
        if 0 <= months <= 16:
            facts.append(f"the author is still actively updating it, with a patch as "
                         f"recent as {_MONTHS[u.month - 1]} {u.year}")
    c = getattr(mod, "created_at", None)
    if c and (date.today().year - c.year) >= 8:
        facts.append(f"it's a genuine classic that's been going strong since {c.year}")
    return facts


def _proof_sentence(mod: Mod, rng: random.Random) -> str:
    """One varied, data-driven 'proof' sentence built from real stats (or '')."""
    facts = _data_facts(mod)
    if not facts:
        return ""
    rng.shuffle(facts)
    pick = facts[:2] if len(facts) >= 2 and rng.random() < 0.5 else facts[:1]
    joined = pick[0] if len(pick) == 1 else f"{pick[0]}, and {pick[1]}"
    frame = rng.choice([
        "To put that in perspective, {f}.",
        "The numbers back it up: {f}.",
        "And it's not just me who rates it — {f}.",
        "For what it's worth, {f}.",
    ])
    return frame.format(f=joined)

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


# Sentences from a mod's summary that are NOT about the mod itself — author
# dedications, donation/Discord begging, changelog/version chatter. Dropped so they
# never reach the narration (the QA gate catches any that slip through).
_OFFTOPIC_SENT = re.compile(
    r"\b(dedicated to|in memory of|rest in peace|my (?:sister|brother|mother|father|"
    r"wife|husband|son|daughter|dog|cat|friend)|patreon|ko-?fi|paypal|donat|"
    r"discord|subscribe|please endorse|endorse if|leave a like|changelog|"
    r"bug ?fix|hotfix|version \d|update \d|requires? )\b", re.I)


def _sentences(text: str, n: int = 2) -> str:
    """Return the first n *complete*, on-topic sentences of cleaned text.

    Nexus summaries are themselves often truncated mid-sentence, so we keep only
    sentences that actually end on terminal punctuation — never invent an ending that
    leaves a dangling fragment like "the arcane arts have now." Off-topic sentences
    (dedications, donation links, changelog notes) are filtered out.
    """
    t = _clean(text)
    # Sentences that end on ./!/? (the regex requires the terminator be present).
    complete = [s.strip() for s in re.findall(r".+?[.!?](?=\s|$)", t)
                if not _OFFTOPIC_SENT.search(s)]
    out = " ".join(complete[:n]).strip()
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
    # Drop a dangling connector left behind by edition-tag removal ("Temple of Agmer for").
    n = re.sub(r"\s+(for|the|of|a|an|and|to|with)$", "", n, flags=re.I).strip(" -–")
    return n or (name or "").strip()


def _clean_author(name: str) -> str:
    """Tidy author display names (drop 'Deleted…User' tombstones and noise)."""
    name = (name or "").strip()
    if not name or re.fullmatch(r"Deleted\d+User", name) or name.lower() == "deleted":
        return "the author"
    return name


def _mod_narration(mod: Mod, rank: int, idx: int, flavour: dict, total: int,
                   category: str, rng: random.Random) -> str:
    """Compose one entry: rank lead-in + name/author + real summary + an editorial
    'who it's for' take + a data-driven proof line. The mix and phrasing are drawn from
    a per-video RNG so segments vary within a video and across videos (anti-template)."""
    author = _clean_author(mod.uploaded_by or mod.author)
    name = _spoken_name(mod.name)
    desc = _sentences(mod.summary, 4)
    values = flavour.get("values", _GENERIC_VALUES)
    who = _WHO_FOR.get(category, _WHO_FOR_GENERIC)
    # Editorial beats: one category value + one "who it's for", phrased from the pools
    # at offsets seeded per video so different uploads don't reuse the same lines.
    # Two distinct category "value" beats + a "who it's for" + a data-proof line, all
    # phrased from per-video-seeded offsets so uploads don't reuse the same lines.
    value = values[(idx + rng.randint(0, len(values) - 1)) % len(values)]
    value2 = values[(idx + rng.randint(0, len(values) - 1)) % len(values)]
    who_line = who[(idx + rng.randint(0, len(who) - 1)) % len(who)]
    proof = _proof_sentence(mod, rng)

    # Editorial beats, de-duplicated so no sentence repeats inside one entry.
    extras = []
    for s in [value, who_line, value2] + ([proof] if proof else []):
        if s and s not in extras:
            extras.append(s)

    def _pad(text: str, target: int) -> str:
        """Top up to ~target words with generic lines not already used (keeps each
        entry long enough to land the video in the 10-15 min band at ~176 wpm)."""
        for cand in rng.sample(_GENERIC_VALUES, len(_GENERIC_VALUES)):
            if len(text.split()) >= target:
                break
            if cand not in text:
                text += " " + cand
        return text

    if rank == 1:
        body = (f"And finally, my number one pick on the whole list: {name} by {author}. "
                + (desc + " " if desc else "") + " ".join(extras)
                + " If you install one single mod from this entire video, make it this "
                "one — it earns the top spot.")
        return _WS.sub(" ", _pad(body, _MIN_WORDS_PER_MOD + 15)).strip()

    lead = _LEADS[(idx + rng.randint(0, len(_LEADS) - 1)) % len(_LEADS)].format(
        o=_ORD.get(rank, str(rank)))
    rng.shuffle(extras)              # vary ordering so the structure isn't identical
    body = f"{lead} {name} by {author}. " + (desc + " " if desc else "") + " ".join(extras)
    return _WS.sub(" ", _pad(body, _MIN_WORDS_PER_MOD)).strip()


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
    nord = _ORD.get(n, str(n))
    # Per-video RNG seeded from the category + part + date, so a given video is stable
    # but different uploads draw different openings, orderings, and phrasings.
    rng = random.Random(f"{category}|{part}|{date.today().isoformat()}|{n}")

    short = noun.replace(" mods", "").title()
    title_options = _unique_titles(category, short, n, year, part, rng)
    title = title_options[0]
    if part and part > 1:
        hook = rng.choice(_HOOKS_PART).format(part=part, n=n, noun=noun, year=year)
    else:
        hook = rng.choice(_HOOKS_FIRST).format(n=n, noun=noun, year=year)

    intro = rng.choice(_INTROS).format(nord=nord)
    outro = rng.choice(_OUTROS).format(n=n, noun=noun, year=year)

    segments = [
        {"kind": "hook", "narration": hook},
        {"kind": "intro", "narration": intro},
    ]
    spec_mods = []
    for idx, mod in enumerate(mods):
        rank = n - idx                       # countdown: first shown is number n
        segments.append({
            "kind": "mod", "ref": idx + 1,
            "narration": _mod_narration(mod, rank, idx, fl, n, category, rng),
        })
        gal = galleries.get(mod.mod_id) or {}
        if isinstance(gal, list):                 # back-compat: bare image list
            gal = {"images": gal, "videos": []}
        urls = []
        if getattr(mod, "picture_url", ""):
            urls.append(mod.picture_url)
        for u in gal.get("images", []) or []:
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
        vids = gal.get("videos", []) or []
        if vids:                                  # real author B-roll, when it exists
            m["video_url"] = vids[0]
            if len(vids) > 1:
                m["video_urls"] = vids[1:3]
        spec_mods.append(m)
    segments.append({"kind": "outro", "narration": outro})

    from ..branding import seo_tags
    slug = f"{date.today().isoformat()}-{category}"
    if part:
        slug += f"-pt{part}"
    return {
        "slug": slug,
        "title": title,
        "title_options": title_options,
        "category_id": category,
        "format": "category_list",
        "hook_line": title_base.replace("Best Skyrim ", "Best "),
        "description": (f"{title}\n\nThe very best {noun} you can play in {year}, "
                        f"counted down from {n} to 1. Every mod is linked below with "
                        f"full credit to its author — go endorse them!"),
        "tags": seo_tags(category),
        "segments": segments,
        "mods": spec_mods,
    }


# High-endorsement entries that are NOT showcase-worthy in a "best of" countdown:
# translations, patches, trackers, markers — they pad the top of the list but make
# for weak video segments. Matched case-insensitively against the mod name.
_JUNK = re.compile(
    r"\b(translation|delayed start|alternate routes?|bugfix|hotfix|"
    r"completion tracker|quest markers?|patch|cleaned|tweaks?|unofficial|"
    r"add-?on)\b", re.I)


def _is_showcase(mod: Mod) -> bool:
    return not _JUNK.search(mod.name or "")


def _base_key(name: str) -> str:
    """Normalised title used to dedupe variants of the same mod (base vs. patch/edition/
    'navmeshed'/translation), so a countdown never features the same content twice."""
    n = re.sub(r"\(.*?\)", " ", name or "").lower()
    n = n.split(" - ")[0]                              # drop "- Navmeshed", "- Reboot"
    n = re.sub(r"\b(sse|se|ae|le|special edition)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def _dedupe(mods: list[Mod]) -> list[Mod]:
    """Keep the first (highest-endorsed) mod per normalised base title."""
    seen, out = set(), []
    for m in mods:
        k = _base_key(m.name)
        if k and k not in seen:
            seen.add(k)
            out.append(m)
    return out


# Nexus has no separate "New Lands" category — new explorable worldspaces and pure
# quest mods both live under "Quests and Adventures". These filters split them so a
# "new lands" video is genuinely new lands (islands/regions/worldspaces), and a
# "quests" video is genuinely quests.
_LAND_NAME = re.compile(
    r"\b(island|isle|isles|lands?|region|realm|continent|shores?|vale|expanse|reach|"
    r"moor|coast|peninsula|archipelago|province|valley|frontier|borderlands|wilds|"
    r"midwood|elsweyr|cyrodiil|morrowind|solstheim|bruma|atmora|akavir)\b", re.I)
_LAND_SUMM = re.compile(
    r"\b(new lands?|worldspace|world space|explorable (?:world|land|island|region)|"
    r"dlc-?sized|adds a (?:new )?(?:land|worldspace|island)|"
    r"brand new (?:land|world|island|region))\b", re.I)
_LAND_EXCL = re.compile(
    r"(\b(quest|questline|murder|contract|dilemma|brotherhood|chapter|tale of|"
    r"prince of|story|romance|mystery|dungeon|barrow|crypt|tomb|cave|ruin|encounter|"
    r"encounters|patch|fix|less rude|navmesh|navmeshed|addon|add-on)\b"
    # language / translation versions of a mod — never feature these:
    r"|\b(spanish|german|russian|french|italian|polish|portuguese|chinese|japanese|"
    r"korean|czech|deutsch|espanol|francais|francaise|italiano|polski|portugues|"
    r"insel|corregido|traduccion|traduzione|traducao|translation|vostfr|"
    r"ru|rus|chs|cht|esp|ger|ita|pol|pl|fra|jp|kr|cz|de|dv|ptbr|nl|tr|hu)\b"
    r"|pt[\s._-]?br|spolszczenie|polski|nederlands|turkce|magyar|"
    r"\bSE-\d|\d+\.\d+)", re.I)        # version numbers ~= reuploads/translations
_QUEST_SIG = re.compile(
    r"\b(quest|questline|adventure|story|mystery|murder|investigat|dark brotherhood|"
    r"thieves guild|companions|college|daedric|questing|side quest|main quest)\b", re.I)


def _is_new_land(mod: Mod) -> bool:
    nm, sm = mod.name or "", mod.summary or ""
    if not nm.isascii() or _LAND_EXCL.search(nm):     # skip foreign-title translations
        return False
    return bool(_LAND_NAME.search(nm) or _LAND_SUMM.search(nm + " " + sm))


def _is_quest(mod: Mod) -> bool:
    nm, sm = mod.name or "", mod.summary or ""
    if _LAND_EXCL.search(nm) or _is_new_land(mod):
        return False                              # pure quests only (not new lands)
    return bool(_QUEST_SIG.search(nm + " " + sm))


_CONTENT_FILTERS = {"new_lands": _is_new_land, "quests": _is_quest}


def next_volume(category: str, domain: str | None = None) -> int:
    """Next volume number for a category's series = highest 'Vol. N'/'Part N' already
    published in that category + 1 (falls back to the video count)."""
    from ..config import channel_config
    from ..history import _load
    domain = domain or channel_config()["channel"]["game_domain"]
    entries = [e for e in _load().get(domain, []) if (e.get("category") or "") == category]
    highest = 0
    for e in entries:
        for m in re.finditer(r"\b(?:vol\.?|part)\s*(\d+)", e.get("title", ""), re.I):
            highest = max(highest, int(m.group(1)))
    return (highest or len(entries)) + 1


def autospec(category: str, count: int = 12, *, domain: str | None = None,
             part: int | None = None, with_gallery: bool = True,
             exclude_ids: set[int] | None = None) -> dict:
    """Discover fresh mods for a category and return a render-ready spec dict.

    `exclude_ids` skips additional mods on top of the no-repeat history — useful for
    generating two back-to-back videos (the second excludes the first's picks).

    Discovery pages deeper automatically until it finds enough *fresh* mods, so a long
    numbered series keeps surfacing new content as the earlier picks fill up history.
    """
    from ..config import channel_config
    from ..history import seen_mod_ids
    from ..research.graphql import discover_mods, graphql_categories_for

    domain = domain or channel_config()["channel"]["game_domain"]
    names = graphql_categories_for(category)
    if not names:
        raise ValueError(f"No GraphQL categories mapped for '{category}'.")
    seen = set(seen_mod_ids(domain)) | set(exclude_ids or set())
    cfilter = _CONTENT_FILTERS.get(category)      # e.g. new-lands-only / quests-only
    fresh: list[Mod] = []
    for pages in (1, 3, 6, 10, 16):
        pool = discover_mods(domain, names, count=max(count * 6, 60), pages=pages)
        fresh = _dedupe([m for m in pool if m.mod_id not in seen and _is_showcase(m)
                         and (cfilter is None or cfilter(m))])
        if len(fresh) >= count:
            break
    chosen = fresh[:count]
    if len(chosen) < count:
        raise ValueError(
            f"Only {len(chosen)} fresh '{category}' mods available (wanted {count}). "
            f"The series has likely exhausted this category's catalogue.")
    # Endorsement DESC means the first item is the strongest; reverse so the
    # countdown climaxes on the single best mod at number one.
    chosen = list(reversed(chosen))
    galleries: dict[int, dict] = {}
    if with_gallery:
        from ..config import load_permissions
        # gallery.py scrapes the mod PAGE (not the API) to get more than the single
        # API picture_url — against Nexus's Acceptable Use Policy, so it only ever
        # runs with explicit opt-in (config/permissions.yaml: allow_gallery_scrape).
        # Off by default -> every mod just keeps its one official API image.
        if load_permissions().get("allow_gallery_scrape"):
            from ..research.gallery import fetch_gallery_media
            max_images = int(load_permissions().get("gallery_max_images", 6))
            for m in chosen:
                try:
                    galleries[m.mod_id] = fetch_gallery_media(
                        m.mod_id, domain, max_images=max_images, max_videos=1)
                except Exception:
                    galleries[m.mod_id] = {"images": [], "videos": []}
    return build_spec(category, chosen, part=part, galleries=galleries)


def write_autospec(category: str, out: str | Path | None = None, **kw) -> str:
    """Generate + write a spec YAML; returns the path."""
    from .manual import write_spec
    spec = autospec(category, **kw)
    out = Path(out) if out else Path("examples") / f"{spec['slug']}.yaml"
    write_spec(spec, out)
    return str(out)
