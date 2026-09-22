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
from html import unescape
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

# Topic bridges. The reference channel rarely announces an entry cold — it links the
# previous mod's subject to the next one ("Talking of Skyrim wildlife, especially
# foxes, next we have...", "From ghosts to grasslands, now let's add..."). Over a
# hundred entries that connective tissue is what keeps a list from reading as a list.
# A bridge is only emitted when a topic is actually detected in BOTH mods, so it can
# never assert a link that isn't there.
_TOPICS = {
    "combat": r"\b(combat|fight|attack|block|parry|stagger|weapon|damage|duel)\w*",
    "followers": r"\b(follower|companion|npc|voice|dialogue|marriage|spouse)\w*",
    "the interface": r"\b(ui|hud|menu|inventory|interface|icon|font)\w*",
    "animation": r"\b(animation|animated|idle|pose|movement|locomotion)\w*",
    "dungeons": r"\b(dungeon|ruin|crypt|barrow|draugr|cave|tomb)\w*",
    "the weather": r"\b(weather|storm|rain|snow|fog|climate|season)\w*",
    "towns and cities": r"\b(town|city|village|hold|whiterun|riften|solitude|markarth)\w*",
    "magic": r"\b(spell|magic|magicka|enchant|conjur|destruction|illusion)\w*",
    "crafting": r"\b(craft|smith|forge|temper|alchemy|potion|cook)\w*",
    "survival": r"\b(survival|hunger|thirst|needs|camping|cold|warmth)\w*",
    "stealth": r"\b(stealth|sneak|thief|thieves|assassin|detect)\w*",
    "creatures": r"\b(creature|beast|dragon|wolf|bear|animal|wildlife|monster)\w*",
    "quests": r"\b(quest|adventure|story|questline|radiant)\w*",
    "the world itself": r"\b(landscape|grass|tree|flora|terrain|worldspace|map)\w*",
}
_TOPICS = {k: re.compile(v, re.I) for k, v in _TOPICS.items()}

_BRIDGE_SAME = ["Speaking of {t}, ", "Staying with {t}, ", "Sticking with {t}, ",
                "Talking of {t}, "]
_BRIDGE_DIFF = ["From {p} to {t}, ", "That's {p} handled — now for {t}. ",
                "We go from {p} to {t} for this one. "]


def _topic_of(mod: Mod) -> str:
    """The first topic whose pattern matches this mod's name or summary, else ""."""
    hay = f"{getattr(mod, 'name', '')} {getattr(mod, 'summary', '')}"
    for topic, pat in _TOPICS.items():
        if pat.search(hay):
            return topic
    return ""


def _bridge(prev: Mod | None, cur: Mod, rng: random.Random) -> str:
    """A connective clause linking the previous entry to this one, or "" when no
    topic is detectable in both — never invent a relationship that isn't there."""
    if prev is None:
        return ""
    p, t = _topic_of(prev), _topic_of(cur)
    if not p or not t:
        return ""
    if p == t:
        return rng.choice(_BRIDGE_SAME).format(t=t)
    return rng.choice(_BRIDGE_DIFF).format(p=p, t=t)

# Category-specific flavour: hook line, what the video is "about", and a pool of
# value sentences rotated through the entries to add variety and pad to length.
_FLAVOUR = {
    "alchemy": {
        "title": "Best Skyrim Alchemy & Enchanting Mods",
        "noun": "alchemy and enchanting mods",
        "subject": "brewing and enchanting",
        "values": [
            "Vanilla alchemy is mostly menu-scrolling, and this is the kind of mod that turns it into something you actually engage with.",
            "It respects the vanilla economy instead of handing you overpowered potions on a plate.",
            "If you've ever ignored the alchemy table for an entire playthrough, this is the mod that changes that.",
            "It's lightweight and lore-friendly, which matters a lot in a school this easy to unbalance.",
            "Enchanting is one of the easiest skills to break, and this keeps it interesting without trivialising the game.",
            "It stacks cleanly with the other mods here, so you can build a full crafting overhaul out of this list.",
        ],
    },
    "vampire": {
        "title": "Best Skyrim Vampire Mods",
        "noun": "vampire mods",
        "subject": "playing a vampire",
        "values": [
            "Vanilla vampirism is mostly a stack of penalties you want cured as fast as possible, and this is the kind of mod that makes it a build instead.",
            "It treats being a vampire as a playstyle with its own rules, rather than a disease with a quest attached.",
            "The feeding loop is the part vanilla never got right, and this is where that finally starts to click.",
            "It fits alongside the bigger vampire overhauls instead of fighting them, which matters in a category this prone to conflicts.",
            "If you've only ever experienced vampirism as the thing you cure in Morthal, this is the mod that changes your mind.",
            "It leans into the predator fantasy without making you unkillable, which is a harder balance than it sounds.",
        ],
    },
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

# Deliberately empty. This used to hold generic value lines ("It's stable,
# well-supported, and beloved for good reason") that _pad() appended until an entry
# hit a word count. That padded runtime with content-free copy, and on a mod with a
# couple of hundred endorsements the claims were simply untrue — both of which the
# narration rules in CLAUDE.md forbid. Length now comes from the mod's own page.
_GENERIC_VALUES: list[str] = []

# "Who it's for" lines add a concrete, opinionated recommendation angle per entry —
# the kind of editorial substance YouTube's inauthentic-content policy looks for.
_WHO_FOR = {
    "vampire": [
        "If you want a vampire playthrough that's a build rather than a debuff, this is for you.",
        "Anyone who plays the Dawnguard side and still wants the vampires to feel dangerous will get a lot out of this.",
        "If your idea of a vampire run is stalking a hold at night rather than sprinting between shadows, this one's aimed at you.",
    ],
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
def _teaser(mods: list[Mod], rng: random.Random) -> str:
    """Name a few of this video's actual standout mods for the opening.

    The strongest pattern in the reference channels' openings is telling the viewer
    what is specifically in THIS episode before the countdown starts, rather than a
    generic "here are N mods". Mods arrive ranked weakest-first, so the tail is the
    good end of the list; naming real entries keeps the promise accurate.
    """
    picks = [_spoken_name(m.name) for m in mods[-3:] if m.name][::-1]
    if not picks:
        return "we've got a stacked list this time"
    if len(picks) == 1:
        return f"we're taking a look at {picks[0]}"
    if len(picks) == 2:
        return f"we're taking a look at {picks[0]} and {picks[1]}"
    return (f"we're taking a look at {picks[0]}, {picks[1]}, {picks[2]}, "
            f"and plenty more")


_HOOKS_FIRST = [
    "Welcome back to the channel! Today we've got {n} of the best {noun} in {year}, "
    "ranked from good all the way up to essential — {teaser}. Every one of them is "
    "free, and every author is credited down in the description. Let's begin.",
    "Hello friends, and welcome back! This time {teaser}, all part of a ranked run "
    "through {n} of the best {noun} you can install in {year}. Everything here is free "
    "and linked below, so go endorse the authors while you watch. Let's get into it.",
    "Welcome back! If your Skyrim is feeling a little stale, this list is the fix: "
    "{n} of the best {noun} in {year}, ranked from good to absolutely essential. "
    "{teaser}. All free, all credited below. Let's begin the first showcase.",
    # Says the quiet part out loud: the countdown already saves the best for last,
    # and the reference channels explicitly promise it rather than leaving it implied.
    "Welcome back! Today we're ranking {n} of the best {noun} in {year}, and "
    "{teaser}. I'm saving my favourite for last, so stick around to the end. "
    "Everything is free and credited below. Let's begin.",
    # Cold open: lead with the observation, identify the video after. Two of the
    # reference videos open this way instead of greeting first.
    "You'd think Skyrim would have run out of good {noun} by {year}. It hasn't — "
    "not even close. {teaser}, and that's only the start of a list {n} deep, "
    "ranked from good to essential. All free, all linked below. Let's get into it.",
    "Skyrim is fourteen years old and somehow the {noun} keep getting better. "
    "{teaser}. That's part of {n} of the best you can install in {year}, ranked "
    "from good all the way to essential, and the best one is last. Let's begin.",
    # Rhetorical question straight to the viewer, answered by the host — one of the
    # reference openings does exactly this before naming the first mod.
    "Are you looking for something new to put in your load order? So am I. So here "
    "are {n} of the best {noun} released in {year}, ranked from good to essential — "
    "{teaser}. All free, all credited below. Let's check out the first one.",
    # Anchored to the moment rather than the game: several of the reference openings
    # start on "a new year is upon us" / "yet another month is drawing to a close".
    "Another year of Skyrim modding is behind us, and honestly it was a good one. "
    "{teaser}. So grab a warm drink and settle in, because we're going through {n} "
    "of the best {noun} of {year}, ranked from good to essential, favourite last. "
    "Let's dive in.",
    # Single-subject shape. Their themed videos don't promise "find a mod", they
    # promise a finished build — "I will be comparing them to each other, to help
    # you build the perfect Whiterun that suits your personal needs" — which is a
    # far stronger payoff when every entry is about one thing.
    "There are more {noun} out there than anyone can reasonably sort through, so "
    "today I'm going through {n} of them, ranked from good to essential. "
    "{teaser}. By the end you'll know exactly which ones belong in your build and "
    "which ones you can skip. Everything is free and credited below. Let's begin.",
]
_HOOKS_PART = [
    "Welcome back — and this time it's part {part}. We've got {n} more of the very best "
    "{noun} Skyrim has to offer, with zero repeats from the earlier videos: {teaser}. "
    "All free, all credited below. Let's begin.",
    "Hello again, friends! Part {part} is here with {n} more of the best {noun} I could "
    "find, and {teaser}. Everything is free and linked in the description. Let's get "
    "straight back into it.",
]
_INTROS = [
    "Quick note before we start: everything here is completely free on Nexus, and every "
    "creator is credited in the description, so please go endorse their work — it's the "
    "least we can do for this much free content. We're counting down from number {nord} "
    "to number one. First off, let's take a look.",
    "One thing up front: a quick endorsement on Nexus genuinely helps these authors keep "
    "going, and they're all linked below. We're going from number {nord} down to number "
    "one, so settle in. Here we go.",
    "Before we dive in — I'm ranking these from number {nord} down to my personal number "
    "one, and you'll absolutely disagree with some of the order, so tell me yours in the "
    "comments. Everything's free and linked below. Now, let's begin.",
    # A tier list's own premise is subjective, and the reference channel's tier video
    # says so out loud and invites the argument rather than waiting to be told:
    # "it's my list, so if you disagree with the placement, please argue with me in
    # the comments." It also states the rubric before the countdown starts.
    "Quick word on how this works. After each mod I'll put it on the tier list: S tier "
    "is for the ones that change how you play the game, down through the middle for "
    "the solid, worth-it picks, and the lower tiers for the narrower mods that are "
    "perfect if they're your thing. It's subjective and it's my list, so if you hate "
    "where something lands, argue with me in the comments — genuinely, I want to hear "
    "it. We're going from number {nord} to number one. Let's begin.",
]
_OUTROS = [
    # The reference outros open on a synthesis beat — what the list adds up to once
    # it's all installed — before any thanks. Then a question to the comments, one
    # like/subscribe ask, and a short sign-off. (Their actual outros are mostly
    # Patreon roll-calls and a recurring host tag; none of that is ours to take.)
    "Put all of these together and it stops being a list of mods — it's a different "
    "Skyrim. Thanks so much for watching. Before you go, I want to know: which of these "
    "is going into your load order first? Tell me in the comments. Everything is linked "
    "below with full credit to the authors, so go endorse them. See you in the next one!",
    "And that's the list. Thanks so much for watching — I hope you found a few new {noun} "
    "for your load order. Every mod is linked below with full credit to the authors who "
    "made them, so go show them some love. Leave a like if you enjoyed this, and "
    "subscribe for more. See you in the next one!",
    "That's all {n} of them. I hope you came away with something new for your next "
    "playthrough — I certainly did. Everything is linked and credited below, so go endorse "
    "the authors; they've earned it. Let me know your own number one in the comments. "
    "Thanks for watching, see you next time!",
    "That wraps up {n} of the best {noun} in {year}. Tell me what you thought of these "
    "in the comment section, and do like and subscribe if you want more lists like this. "
    "All the authors are credited down below. Thank you so much for watching — see you "
    "in the next one!",
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
# Mod page bodies are BBCode *and* HTML — "<br />" read aloud is not a sentence.
_HTML = re.compile(r"<[^>]+>")
# All-caps run-in headers authors use to structure a page ("DESCRIPTION:",
# "FEATURES -"). Spoken, they're noise in the middle of a sentence.
_HEADER = re.compile(r"\b[A-Z][A-Z &'/-]{3,}\s*[:\-–]\s*")


def _clean(text: str) -> str:
    """Strip BBCode/HTML/URLs/markup noise from Nexus copy and tidy whitespace."""
    t = _BBCODE.sub("", text or "")
    t = _HTML.sub(" ", t)
    t = unescape(t)                                 # &nbsp;, &amp;, &#8203; …
    t = t.replace("​", " ").replace("﻿", " ")   # zero-width junk
    t = _HEADER.sub("", t)
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
    r"bug ?fix|hotfix|version \d|update \d)\b", re.I)
# "requires ..." was in the list above, which threw away exactly the detail the
# narration rules ask for — a named requirement ("requires SKSE and Address
# Library") is a concrete specific, and the reference channel states them. It also
# lets an author's own compatibility warning through, which is the one honest way
# to give an entry a caveat without inventing a flaw.


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


# Spoken tier verdicts. The reference channel's own tier-list video states a
# placement out loud after every showcase, with a reason and usually a caveat —
# "Bottom of the Well goes to Hearthfire Comfort tier: it has a great location and
# convenience, plausible lore, and great compact detailing, but navmeshing is not
# great." Our tier-list videos put the tier on a card and never said why, which left
# the format's central claim unargued. These justify the placement from what we
# actually know (where the mod sits in the ranking), never from invented specifics.
_VERDICT_TOP = [
    "{name} goes straight into {tier} tier — this is the level where a mod stops "
    "being a nice addition and starts being part of how you play.",
    "That puts {name} in {tier} tier for me. Very little on this list is doing "
    "something this substantial.",
]
_VERDICT_MID = [
    "{name} lands in {tier} tier: genuinely good, and it earns its place, but it "
    "isn't reshaping your game the way the top of this list does.",
    "I'm putting {name} in {tier} tier — solid, well-liked, and worth the slot, "
    "just short of essential.",
]
_VERDICT_LOW = [
    "{name} sits in {tier} tier. It does one thing, it does it well, and whether "
    "you want it comes down to whether you want that one thing.",
    "That's {tier} tier for {name} — a narrow pick rather than a load-order "
    "staple, but the right choice for the right playthrough.",
]


def tier_verdict(name: str, tier: str, rank: int, total: int,
                 rng: random.Random | None = None) -> str:
    """One spoken sentence placing a mod in its tier, for `ranked_tier_list` specs.

    `rank` is the countdown position (1 = best), so the pool is chosen by where the
    entry actually sits. The claim is about the ranking, which we know, rather than
    about the mod's internals, which we would have to invent.
    """
    rng = rng or random.Random(f"{name}|{tier}|{rank}")
    frac = 1.0 - ((rank - 1) / max(total - 1, 1))    # 1.0 = best entry
    pool = _VERDICT_TOP if frac >= 0.72 else (_VERDICT_MID if frac >= 0.38
                                              else _VERDICT_LOW)
    return rng.choice(pool).format(name=_spoken_name(name), tier=tier)


def _clean_author(name: str) -> str:
    """Tidy author display names (drop 'Deleted…User' tombstones and noise)."""
    name = (name or "").strip()
    if not name or re.fullmatch(r"Deleted\d+User", name) or name.lower() == "deleted":
        return "the author"
    return name


def _mod_narration(mod: Mod, rank: int, idx: int, flavour: dict, total: int,
                   category: str, rng: random.Random, prev: Mod | None = None) -> str:
    """Compose one entry: rank lead-in + name/author + real summary + an editorial
    'who it's for' take + a data-driven proof line. The mix and phrasing are drawn from
    a per-video RNG so segments vary within a video and across videos (anti-template)."""
    author = _clean_author(mod.uploaded_by or mod.author)
    name = _spoken_name(mod.name)
    desc = _sentences(mod.summary, 4)
    values = flavour.get("values", [])
    who = _WHO_FOR.get(category, _WHO_FOR_GENERIC)
    # One category value beat and one "who it's for" — opinion, which the reference
    # channel does give. What it never does is pad with content-free lines, so there
    # is exactly one of each and the rest of the entry is the mod's own detail.
    value = values[(idx + rng.randint(0, len(values) - 1)) % len(values)] if values else ""
    who_line = who[(idx + rng.randint(0, len(who) - 1)) % len(who)]
    proof = _proof_sentence(mod, rng)

    # Editorial beats, de-duplicated so no sentence repeats inside one entry.
    extras = []
    for s in [value, who_line] + ([proof] if proof else []):
        if s and s not in extras:
            extras.append(s)

    def _pad(text: str, target: int) -> str:
        """Top up to ~target words with more of the mod's OWN description.

        The reference channel fills a segment with specifics — counts, options,
        requirements, how you actually get the thing in game — so this mines further
        into the mod page rather than appending generic filler. An entry whose page
        has nothing more to say simply comes out shorter; that is the correct
        outcome, and padding it was both invented content and, for a mod with a
        couple of hundred endorsements, factually wrong.
        """
        have = set(text.split("."))
        for sent in re.findall(r".+?[.!?](?=\s|$)", _clean(mod.description)):
            if len(text.split()) >= target:
                break
            s = sent.strip()
            if (len(s.split()) >= 6 and s not in have
                    and not _OFFTOPIC_SENT.search(s) and s not in text):
                text += " " + s
        return text

    if rank == 1:
        body = (f"And finally, my number one pick on the whole list: {name} by {author}. "
                + (desc + " " if desc else "") + " ".join(extras)
                + " If you install one single mod from this entire video, make it this "
                "one — it earns the top spot.")
        return _WS.sub(" ", _pad(body, _MIN_WORDS_PER_MOD + 15)).strip()

    lead = _LEADS[(idx + rng.randint(0, len(_LEADS) - 1)) % len(_LEADS)].format(
        o=_ORD.get(rank, str(rank)))
    # Bridge roughly every third entry: the reference channel uses these to break up a
    # run of cold announcements, not on every single one, which would be its own tic.
    bridge = _bridge(prev, mod, rng) if idx % 3 == 1 else ""
    if bridge:
        # Only a bridge that hands off mid-sentence ("Speaking of combat, ") lowercases
        # the lead; one that closes its own sentence must leave it capitalised.
        joins_mid = bridge.rstrip().endswith(",")
        lead = bridge + (lead[0].lower() + lead[1:] if joins_mid else lead)
    rng.shuffle(extras)              # vary ordering so the structure isn't identical
    body = f"{lead} {name} by {author}. " + (desc + " " if desc else "") + " ".join(extras)
    return _WS.sub(" ", _pad(body, _MIN_WORDS_PER_MOD)).strip()


def _to_all_time(text: str, year: int) -> str:
    """Rewrite a year-scoped opening into an all-time one.

    The templates say things like "the best vampire mods in 2026" and "released in
    2026". On a list that spans the whole of Skyrim modding those are false, and a
    viewer notices immediately when the number one entry is eight years old.
    """
    y = str(year)
    for a, b in ((f"in {y}", "of all time"), (f"of {y}", "of all time"),
                 (f"by {y}", "by now"), (f"released in {y}", "ever released"),
                 (f"install in {y}", "install today"),
                 (f"you can play in {y}", "you can play")):
        text = text.replace(a, b)
    # A leftover bare year ("Another year of Skyrim modding…") would still date it.
    text = re.sub(rf"\b{y}\b", "all time", text)
    return re.sub(r"\ball time all time\b", "all time", text)


def build_spec(category: str, mods: list[Mod], *, part: int | None = None,
               flavour: dict | None = None,
               galleries: dict[int, list[str]] | None = None,
               all_time: bool = False) -> dict:
    """Assemble a full script spec (hook/intro/countdown/outro) from ranked mods.

    `all_time` is for a list that isn't scoped to a year ("best vampire mods of all
    time"). Every hook and outro template interpolates the current year, so without
    it an all-time episode opens by calling itself a {year} list, which is simply
    wrong.
    """
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
    def _caps(text: str) -> str:
        """Capitalise after sentence breaks — the teaser is a lower-case clause and
        templates may drop it either mid-sentence or at the start of one."""
        return re.sub(r"([.!?]\s+)([a-z])",
                      lambda m: m.group(1) + m.group(2).upper(), text)

    teaser = _teaser(mods, rng)
    if part and part > 1:
        hook = _caps(rng.choice(_HOOKS_PART).format(part=part, n=n, noun=noun,
                                                    year=year, teaser=teaser))
    else:
        hook = _caps(rng.choice(_HOOKS_FIRST).format(n=n, noun=noun, year=year,
                                                     teaser=teaser))

    intro = rng.choice(_INTROS).format(nord=nord)
    outro = rng.choice(_OUTROS).format(n=n, noun=noun, year=year)

    if all_time:
        hook, outro = (_to_all_time(hook, year), _to_all_time(outro, year))

    segments = [
        {"kind": "hook", "narration": hook},
        {"kind": "intro", "narration": intro},
    ]
    spec_mods = []
    for idx, mod in enumerate(mods):
        rank = n - idx                       # countdown: first shown is number n
        segments.append({
            "kind": "mod", "ref": idx + 1,
            "narration": _mod_narration(mod, rank, idx, fl, n, category, rng,
                                        prev=mods[idx - 1] if idx else None),
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
