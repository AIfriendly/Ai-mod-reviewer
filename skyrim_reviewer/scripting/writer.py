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

from ..config import require_env
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
3. MOD SEGMENTS (one per mod, kind="mod"): For each mod, in ranked order — what
   it does, why it matters, the single coolest detail, and a smooth transition to
   the next. Lead segments are punchy; give the top 2-3 mods a longer beat. Every
   segment must CREDIT the mod author by name (the credit is also shown on
   screen, but say it too). End most segments with a mini-hook ("but this next
   one is the reason I made the video").
4. OUTRO (one segment, kind="outro"): Quick recap, a clear CTA to subscribe, and
   tease NEXT week's topic by name.

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

# JSON schema for structured output (mirrors models.Script / models.Segment).
_OUTPUT_SCHEMA = {
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
                "properties": {
                    "segment_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["hook", "intro", "mod", "outro"]},
                    "title": {"type": "string"},
                    "narration": {"type": "string"},
                    "target_seconds": {"type": "number"},
                    "mod_id": {"type": ["integer", "null"]},
                },
                "required": ["segment_id", "kind", "title", "narration",
                             "target_seconds", "mod_id"],
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
        output_config={"format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
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
