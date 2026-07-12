# Script style study — top Skyrim-mod channels

Distilled from 5 high-performing SoftGaming videos (17k–48k views, 9–13 min,
~1500–2000 words, ~155–160 wpm) pulled via yt-dlp. This is the playbook the script
writer (`scripting/writer.py`) and any hand-authored `--script` spec should follow.

## The hook (first ~30s)
- Open COLD. No "hey guys / welcome back". Straight into value.
- Establish authority + a promise, then tease the payoff:
  - Evergreen: *"Skyrim modding has been part of my life for over a decade, and a
    select few mods have become what I consider the best of all time… except the last
    one, which is my favourite ever made."*
  - New/roundup: *"Skyrim modding is more exciting than ever — incredible new mods
    are being released almost daily. Let's dive in."*

## Per-mod: the 4-beat structure (the core lesson)
Every mod segment follows the same shape — this is what separates these scripts from
generic "this mod adds X" narration:
1. **The vanilla problem** — the specific pain the mod fixes. *"In vanilla Skyrim
   every container interrupts you with a full inventory menu."* The vanilla-vs-modded
   **contrast** is the strongest single device; use it constantly.
2. **What it does** — concrete, named mechanics (the MCM, stamina cost, timed block,
   perk system), never vague hype. Author credited inline and naturally: *"the new
   Windhelm overhaul by Tomato."*
3. **Why it matters** — the real payoff. *"Over one playthrough this saves you hours
   of menus"; "makes each ruin feel alive to explore again."*
4. **Transition** — contextual, varied hand-off: *"Sticking with combat…", "When it
   comes to armour…", "But my favourite is still to come."* Never a bare "number nine".

## Voice & trust
- **Honest micro-caveats build trust** (the r/skyrimmods audience punishes hype):
  *"this one's a bit controversial", "the default settings felt too forgiving, I'd
  reduce the timing windows", "does not work while dual-wielding."* Never all-positive.
- First-person authority + personal takes: *"in my experience", "quickly became a
  favourite of mine", "in my opinion."*
- Specific over generic. Name features, numbers, real consequences.
- Group thematically (UI → animation → combat → visuals) rather than a rigid numeric
  countdown; let transitions signal the grouping.

## CTAs & outro
- Keep CTAs OUT of the body — no repeated "go endorse / subscribe" mid-video. Body
  stays value-dense.
- Outro = one recap line + ONE clear CTA (comment your favourite + subscribe) + tease
  next topic + a short signature signoff (*"Happy modding, everyone."*)

## Pacing
- ~155–160 wpm. 9–13 min total. ~150–200 words per mod; give the top 2–3 a longer beat.

## Where we differed (fixes applied)
- We used a rigid "Number N" countdown + templated value sentences + repeated
  "go endorse". → Moved to problem→mechanics→payoff→contextual-transition, honest
  caveats, CTAs only in the outro. Encoded in `scripting/writer.py` SYSTEM_PROMPT.
