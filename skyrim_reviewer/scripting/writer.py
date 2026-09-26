"""Script-generation stage — turns a ranked mod list into a narrated video script.

Uses the Anthropic Claude API (model claude-opus-4-8) with:
  * a large STATIC system prompt (style guide + structure rules) marked for
    prompt caching, so every weekly run re-reads it at ~0.1x cost;
  * structured JSON output (output_config.format) so we get back exactly the
    Script/Segment shape the rest of the pipeline expects;
  * adaptive thinking, which lets the model plan pacing without a token budget.

The system prompt is frozen — all volatile content (the mods, the profile, the
category) lives in the user message, AFTER the cache breakpoint.
"""
from __future__ import annotations

import json

import anthropic

from ..config import channel_config, require_env
from ..models import Mod, Script, Segment, VideoFormat, VideoProfile

MODEL = "claude-opus-4-8"

# --- STATIC system prompt (cached). Do NOT interpolate per-request data here. ---
SYSTEM_PROMPT = """\
You are the head writer for a YouTube channel that reviews Skyrim mods. You write
the spoken narration script for long-form showcase videos. Your scripts are read
aloud by a single narrator (the channel owner's cloned voice), so write for the
EAR, not the eye: conversational, energetic, second-person, contractions, short
sentences. No stage directions, no markdown, no emoji in the narration text.

RESEARCH-BACKED STRUCTURE (follow exactly):
1. HOOK (one segment, kind="hook"): Open COLD on the single most visually
   impressive mod. No channel intro, no "hey guys". First sentence must create a
   curiosity gap or make a bold promise. ~25-30 words.
2. INTRO (one segment, kind="intro"): State the promise of the video ("X mods
   that..."), then a quick pattern interrupt. Tease the best mod is saved for
   last. ~45-60 words.
3. MOD SEGMENTS (one per mod, kind="mod"): Write each mod on this proven 4-beat
   structure (studied from top-performing Skyrim-mod channels):
     a. THE VANILLA PROBLEM — open on the specific pain point the mod fixes ("In
        vanilla Skyrim, every container interrupts you with a full inventory menu").
        This contrast (vanilla vs modded) is the single strongest device — use it.
     b. WHAT IT DOES — the actual mechanics, named and CONCRETE (the MCM, the
        stamina cost, the perk system), not vague hype. Credit the author by name
        inline and naturally ("the new Windhelm overhaul by Tomato").
     c. WHY IT MATTERS — the deeper payoff in real terms ("over one playthrough
        this saves you hours of menus"; "makes each ruin feel alive to explore").
     d. TRANSITION — a smooth, contextual hand-off ("Sticking with combat...",
        "When it comes to armour...", "But my favourite is still to come"). Do NOT
        just say "Number nine"; vary the connective tissue.
   Give the top 2-3 mods a longer beat. Where a mod has a real caveat (finicky
   compatibility, controversial, a downside), SAY SO briefly — honest micro-caveats
   ("this one's a bit controversial", "the default settings felt too forgiving")
   build the trust that the r/skyrimmods audience rewards. Never all-positive hype.
4. OUTRO (one segment, kind="outro"): One clean recap line, ONE clear CTA (comment
   your favourite + subscribe), and tease NEXT week's topic by name. Do not repeat
   "go endorse" throughout the video — keep CTAs to the outro so the body stays value-
   dense. A short signature signoff is good ("Happy modding, everyone").

PACING: Narration length must fit each segment's target_seconds at ~155 words per
minute. A 60-second segment is ~155 words; a 100-second segment ~260 words. Do
not pad with filler; if a mod is thin, keep its segment tighter.

TITLE: Use a high-CTR template appropriate to the format (numbers, "you NEED",
year tag, curiosity gap). Keep under 70 characters. Be honest — no overpromising
the r/skyrimmods community would mock.

DESCRIPTION: 2-3 sentence YouTube description + a "Mods featured (credit to their
authors):" list is added programmatically, so do NOT list the mods yourself —
just write the prose description and tags.

CHAPTERS: Provide a chapter label per segment ("Intro", the mod name, "Outro").
Timestamps are computed later from real audio durations — labels only, no times.

Return ONLY the structured object requested. mod_id on a "mod" segment MUST match
the mod_id you were given for that mod."""

def _build_output_schema(criteria: list[str] | None = None) -> dict:
    """JSON schema for structured output (mirrors models.Script / models.Segment).

    `criteria` (from config channel.yaml -> tier_list.scorecard_criteria) adds the
    ranked_tier_list-only verdict fields (tier/scorecard/best_for) to every segment,
    with `scorecard` locked to exactly those criterion names. Other formats simply
    leave tier=null, scorecard={}, best_for="" — the schema still declares the fields
    (additionalProperties: False requires it) but nothing forces them to be used."""
    seg_props = {
        "segment_id": {"type": "string"},
        "kind": {"type": "string", "enum": ["hook", "intro", "mod", "outro"]},
        "title": {"type": "string"},
        "narration": {"type": "string"},
        "target_seconds": {"type": "number"},
        "mod_id": {"type": ["integer", "null"]},
        "tier": {"type": ["string", "null"],
                 "description": "ranked_tier_list only: this mod's tier verdict"},
        "scorecard": {
            "type": "object",
            "additionalProperties": False,
            "properties": {c: {"type": "number"} for c in (criteria or [])},
            "required": list(criteria or []),
            "description": "ranked_tier_list only: 0-5 (allow .5) per criterion; "
                            "{} for non-mod segments or other formats",
        },
        "best_for": {"type": "string",
                     "description": "ranked_tier_list only: one-line 'who this is for'"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "hook_line": {"type": "string", "description": "Short title-card hook, <= 8 words"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": seg_props,
                    "required": ["segment_id", "kind", "title", "narration",
                                 "target_seconds", "mod_id", "tier", "scorecard",
                                 "best_for"],
                },
            },
        },
        "required": ["title", "hook_line", "description", "tags", "segments"],
    }


# Format-specific structure notes appended to the (volatile) user prompt.
_FORMAT_GUIDANCE = {
    VideoFormat.transformation: (
        "This is a TRANSFORMATION video — not a list. Treat it as a cinematic "
        "journey that turns Skyrim into the target game. The HOOK opens on the "
        "contrast (drab vanilla vs the new world) and poses the fantasy. Then move "
        "through the world aspect by aspect — the LOOK (visuals/ENB), the WORLD "
        "(locations), the PEOPLE (characters/armor), the FEEL (combat), the SOUND — "
        "weaving the mods into each beat rather than numbering them 1..N. The OUTRO "
        "lands the payoff: Skyrim is gone, this is the new game now."
    ),
    VideoFormat.weekly_roundup: (
        "This is a weekly roundup of fresh mods — keep energy high and segments "
        "tight; assume returning subscribers who want what's NEW this week."
    ),
    VideoFormat.ranked_tier_list: (
        "This is a RANKED TIER LIST, not a listicle. METHODOLOGY FIRST: the INTRO "
        "must state, before any mod is discussed, that every mod here was actually "
        "played, that placement is personal opinion (not a judgement of the author's "
        "skill), and that each one will land on a tier list by the end — set this "
        "expectation before segment 1, not after. Each MOD segment follows this exact "
        "beat order: (a) name + one-line premise, (b) what it's actually like to play "
        "it, first person, concrete not hypey, (c) ONE specific memorable moment or "
        "anecdote, (d) an explicit comparison to the mod covered in the PREVIOUS "
        "segment ('this feels completely different from...' / 'like <previous mod>, "
        "but...') — this is what makes segments feel connected instead of a flat "
        "list, (e) a brief who-it's-for caveat, (f) the tier verdict as its own "
        "single declarative sentence ('So I'm putting <mod> in <tier> tier.'). Give "
        "ties/nuance where earned ('right at the top of A, just under S') rather than "
        "a flat slot. The OUTRO shows the completed board, admits it isn't every mod "
        "in the category, and explicitly asks the audience which mod has to be in a "
        "follow-up — this seeds the sequel."
    ),
}


def _build_user_prompt(category_title: str, fmt: VideoFormat, profile: VideoProfile,
                       mods: list[Mod], next_topic: str, theme: str) -> str:
    lines = [
        f"Write the script for a ~{profile.target_minutes}-minute Skyrim mod "
        f"showcase video.",
        f"Format: {fmt.value}.",
        f"Working title topic: {category_title}.",
    ]
    if fmt in _FORMAT_GUIDANCE:
        lines.append(_FORMAT_GUIDANCE[fmt])
    if fmt == VideoFormat.ranked_tier_list:
        tl = channel_config().get("tier_list", {})
        tiers = tl.get("tiers", ["S", "A", "B", "C"])
        criteria = tl.get("scorecard_criteria", [])
        lines.append(
            f"Tiers, hottest first: {', '.join(tiers)}. Every mod segment's `tier` "
            f"must be one of these. Score every mod on exactly these criteria (0-5, "
            f".5 allowed) in `scorecard`: {', '.join(criteria)}. Fill `best_for` with "
            f"one honest line naming the kind of player this mod suits best. On "
            f"hook/intro/outro segments, leave tier null, scorecard {{}}, best_for \"\"."
        )
    if theme:
        lines.append(f"Transformation theme: {theme}.")
    lines += [
        "",
        "Segment time budget (use these for target_seconds):",
        f"  hook: {profile.hook_seconds}s, intro: {profile.intro_seconds}s, "
        f"each mod: ~{profile.seconds_per_mod}s, outro: {profile.outro_seconds}s.",
        f"Feature exactly these {len(mods)} mods, in this ranked order "
        f"(give mod_id verbatim on each mod segment):",
        "",
    ]
    for i, m in enumerate(mods, 1):
        summary = (m.summary or "").strip().replace("\n", " ")
        if len(summary) > 400:
            summary = summary[:400] + "…"
        author = m.uploaded_by or m.author or "Unknown"
        lines.append(
            f"{i}. mod_id={m.mod_id} | \"{m.name}\" by {author} | "
            f"{m.endorsements} endorsements | {summary or 'No summary provided.'}"
        )
    lines += [
        "",
        f"Tease this as NEXT week's topic in the outro: {next_topic}.",
    ]
    # AUDIENCE INSIGHTS from the channel's own analytics (`skyrim-reviewer learn`).
    # Volatile, so it lives in the user turn — the cached system prompt stays frozen.
    try:
        from ..analytics import load_insights
        guidance = load_insights().get("script_guidance") or []
    except Exception:
        guidance = []
    if guidance:
        lines += ["", "AUDIENCE INSIGHTS (measured on this channel's own videos):"]
        lines += [f"- {g}" for g in guidance]
    return "\n".join(lines)


def write_script(
    mods: list[Mod],
    *,
    category_title: str,
    fmt: VideoFormat,
    profile: VideoProfile,
    next_topic: str = "more game-changing Skyrim mods",
    theme: str = "",
    client: anthropic.Anthropic | None = None,
) -> Script:
    """Generate a full narration Script for the given mods."""
    client = client or anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))
    user_prompt = _build_user_prompt(category_title, fmt, profile, mods, next_topic, theme)
    criteria = channel_config().get("tier_list", {}).get("scorecard_criteria", [])

    # Static system prompt is cached; volatile mod list is in the user turn.
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
        output_config={"format": {"type": "json_schema",
                                   "schema": _build_output_schema(criteria)}},
    )

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    segments = [Segment(**s) for s in data["segments"]]
    # Attach the YouTube credit block to the description (we add the list, not Claude).
    credits = "\n".join(f"• {m.credit_line()}" for m in mods)
    description = (
        data["description"].strip()
        + "\n\nMods featured (full credit to their authors):\n" + credits
    )
    return Script(
        title=data["title"],
        format=fmt,
        hook_line=data["hook_line"],
        description=description,
        tags=data.get("tags", []),
        chapters=[s.title for s in segments],
        segments=segments,
    )
