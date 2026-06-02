# 🐉 AI Skyrim Mod Review Generator

Researches the best Skyrim mods, writes a narration script with Claude, narrates
it in **your cloned voice**, edits a finished YouTube video with **moviepy +
ffmpeg** (Ken Burns on stills, music bed, captions), renders polished **Remotion**
title cards, and generates a **before/after thumbnail** — all from one command.

```bash
skyrim-reviewer make weapons            # 5-min test video (default)
skyrim-reviewer make weapons --profile full   # 20-min video once you're happy
```

---

## Research-backed strategy (why it's built this way)

A deep research pass (Reddit r/skyrimmods + r/NewTubers, creator case studies,
2024–2026) drove these defaults. Full sourcing lives in the answers baked into
`config/channel.yaml`, but the short version:

| Decision | Finding |
|---|---|
| **Format = Hybrid** | Evergreen **"Best [category] Mods"** lists are the growth backbone (people search them for years); **"Transforming Skyrim into X"** videos are the viral spikes; **weekly roundups** decay fast — use sparingly. |
| **~20 min** | Long enough for 2–3 mid-roll ads. Structure: cold hook (no logo intro) → promise → 8–12 mods @ ~85–125s → save a banger for last → CTA. Start with **5-min test** videos to validate quality. |
| **Titles/thumbnails** | `"N Skyrim X Mods You NEED in 2026"`, before/after split thumbnails (~+35% CTR for graphics mods), 0–3 words of big bold text, high contrast. |
| **Footage** | Successful channels record their own gameplay. **NexusMods' API forbids scraping/rehosting media**, and authors own their uploads — so this tool only pulls media for mods you've recorded as permission-approved, always credits authors, and uses placeholder slates otherwise. |
| **Cadence** | 1 long video/week is a viable solo floor; supplement with Shorts. Skyrim modding is still a healthy, active niche. |

> ⚖️ **Footage & music are the legal-sensitive parts.** This tool is built to keep
> you compliant (official API only, permission ledger, on-screen + description
> credits, royalty-free music folder). It is not legal advice — fair use is
> case-by-case. When in doubt, record your own gameplay.

---

## Footage (fully automated, mod images via the API)

This channel uses the one footage source that's both **legal and fully automated**:
the single main image the **official NexusMods API** exposes per mod. No scraping,
no recording, no ripping other creators.

A static still over a 60s segment would tank retention, so the editor turns each
image into **multi-shot Ken Burns** — several distinct camera moves (different
crops, zoom directions, focus points) hard-cut together — so one screenshot plays
like b-roll. (`config/channel.yaml` → `video.shot_seconds` controls the pace; a new
move ~every 16s.)

Footage resolution order per segment: author-permitted **video clip** (if you ever
add one) → **mod image** (multi-shot Ken Burns) → **placeholder slate**.

**Permissions** — mods only show their image if the author allows reuse (they own
their uploads). Two ways:

```bash
skyrim-reviewer approve VividWeathers     # author permitted media reuse (recommended)
skyrim-reviewer approve 266               # or approve a specific mod id
```

…or, for hands-off automation, set `assume_all_permitted: true` in
`config/permissions.yaml` (informed opt-in — every author is still credited on
screen + in the description, but some may not want reuse; you accept that risk).
Either way unapproved mods fall back to a neutral credited slate.

## Pipeline

```
research → script → assets → voice → edit → package
  │         │         │        │       │       │
NexusMods  Claude   permitted  your   moviepy  Remotion title card
API ranks  writes   media +    cloned ffmpeg   + before/after thumbnail
best mods  the      credits    voice  Ken Burns  + .srt + chapters
           script              (TTS)  + music
```

Each stage saves to `work/<slug>/state.json`, so stages are resumable.

---

## Setup

```bash
# 1. Python deps
pip install -r requirements.txt

# 2. ffmpeg — system install preferred; otherwise imageio-ffmpeg (in requirements)
#    provides a bundled binary automatically.
#    Debian/Ubuntu: sudo apt-get install ffmpeg

# 3. Keys
cp .env.example .env      # then fill in ANTHROPIC_API_KEY, NEXUS_API_KEY, voice keys

# 4. (Optional) Remotion title cards
cd remotion && npm install && cd ..
```

### Voice

Edit `config/voice.yaml` → `provider:` and fill the matching section. Options:
`elevenlabs` (your cloned voice — set `voice_id` or `ELEVENLABS_VOICE_ID`),
`openai`, `prerecorded` (drop `work/narration/<segment_id>.wav` files), or
**`piper`** for a fully local, free, offline voice (no keys):

```bash
# Local Piper voice (the channel's default for zero-cost rendering)
pip install piper-tts
python -m piper.download_voices en_US-ryan-high --download-dir voices
# config/voice.yaml -> provider: piper  (model_path: voices/en_US-ryan-high.onnx)
```

> MoviePy 1.x + Pillow ≥10: the `ANTIALIAS` constant was removed in Pillow 10;
> `skyrim_reviewer/edit/pil_compat.py` restores it automatically, so renders work
> on modern Pillow with no pin.

### Permissions ledger

Record which mod authors let you feature their media in `config/permissions.yaml`.
Until a mod is approved there, the pipeline shows a neutral placeholder slate for
it (so you can build and test the whole video before chasing permissions).

---

## Usage

```bash
skyrim-reviewer categories                 # list category buckets
skyrim-reviewer research weapons           # see the ranked mods
skyrim-reviewer script weapons             # research + print the script (no render)
skyrim-reviewer make weapons               # full pipeline, 5-min test profile
skyrim-reviewer make graphics --profile full
```

### No-API-key path (script authored in chat)

You don't need an Anthropic key. Author the script (research + narration) as a
YAML spec — mods can be embedded inline, so it runs with **no API keys at all**
(only a voice). A complete worked example ships in `examples/`:

```bash
skyrim-reviewer make the-witcher --fmt transformation \
    --script examples/transforming_skyrim_witcher.yaml
```

See `skyrim_reviewer/scripting/manual.py` for the spec format.

### "Transforming Skyrim into X" template

Transformation videos are the viral-spike format. `config/transformations.yaml`
defines the cinematic pillars (Look → World → People → Feel → Sound), themes
(Witcher, Elden Ring, GoT, LOTR, Bloodborne) and title templates. The intro is
built to open on the vanilla-vs-modded contrast, and the Remotion title card is a
kinetic ember-lit reveal.

Output lands in `output/<slug>.mp4` with a matching `.srt`, `.description.txt`
(title + description + accurate chapters), and `work/<slug>/thumbnail.png`.

---

## Configuration

| File | Controls |
|---|---|
| `config/channel.yaml` | Niche, categories, video profiles (test/full), ranking weights, branding, title templates |
| `config/voice.yaml` | TTS provider + your cloned-voice settings |
| `config/permissions.yaml` | Which mods/authors approved media reuse |
| `.env` | API keys |

---

## Project layout

```
skyrim_reviewer/
  research/nexus.py     NexusMods API client + ranking (AUP-compliant)
  scripting/writer.py   Claude script generation (prompt caching + structured output)
  assets/media.py       Permission-gated media download + credits manifest
  voice/                Pluggable TTS (elevenlabs/openai/piper/prerecorded)
  edit/                 Ken Burns, lower-thirds, music, captions, assembly
  thumbnail/generate.py Before/after thumbnail
  pipeline.py / cli.py  Orchestration + CLI
remotion/               Animated title cards (React/Remotion)
```

---

## Status

Working stage implementations. Two ways to run:

- **Chat-authored (no API keys):** use `--script <spec.yaml>` (see `examples/`).
  Only a voice is required to produce a finished video; placeholder slates cover
  any mod without permitted media.
- **Automated:** add `ANTHROPIC_API_KEY` (script writer) + `NEXUS_API_KEY`
  (research) to fetch and write everything programmatically.

Either way, configure a voice in `config/voice.yaml` and add permission entries in
`config/permissions.yaml` for any mod whose media you want to show on screen.
