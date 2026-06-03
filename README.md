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

Each image is shown **whole** (fitted, never cropped) over a softly blurred fill of
itself, with a **documentary-style Ken Burns move — combined zoom + pan** (left/right/
up/down), like a History-Channel doc rather than a flat zoom. A single still is split
into a couple of distinct moves; when a mod has several images, the editor cycles
through them.

**Cinematic intro.** Instead of jumping into the topic, the cold open plays a montage
of official Skyrim **gameplay-trailer B-roll** (pulled from Steam's public API, cached)
that **cuts to a different clip every ~5 seconds**, with the title + a spoken hook over
it. Logo/rating screens and black fades are filtered out. See
`skyrim_reviewer/research/footage.py`. Trailer footage is Bethesda's IP (monetised
Skyrim videos are permitted, but keep clips short to limit Content-ID risk).

**Music.** Royalty-free fantasy/epic tracks (not the Skyrim OST, which gets Content-ID
claimed). Run `skyrim-reviewer fetch-music` to download the default Kevin MacLeod
CC BY 4.0 set into `music/`; the chosen track is credited automatically in the
description. Drop your own tracks in `music/` to use them instead.

**Video ideas.** `skyrim-reviewer ideas` generates viral-style titles + hooks modeled
on top mod channels (Heavy Burns, Brodual, MxR, Mern, …) crossed with your categories,
each with the exact `make` command to produce it. Edit `config/reference_channels.yaml`
to tune the channels/formats. Add `--live` to name real currently-trending mods.

> **Why only one image per mod?** The official API (v1 REST and v2 GraphQL) exposes
> exactly one `picture_url` per mod — the full screenshot gallery lives only on the
> mod's website page, which the API does not expose. Getting the rest requires
> reading the page (see *Gallery scraping* below).

Footage resolution order per segment: author-permitted **video clip** → **mod
image(s)** (fit + gentle Ken Burns) → **placeholder slate**.

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

### Gallery scraping (⚠️ ToS-violating, off by default)

To get **many** images per mod, set `allow_gallery_scrape: true` (and
`gallery_max_images`) in `config/permissions.yaml`. The asset stage then reads each
**approved** mod's website page and pulls its full image gallery (see
`skyrim_reviewer/research/gallery.py`).

This breaks the NexusMods API/ToS, and **the account behind your API key could be
banned**. It's polite (browser UA, backoff) and only runs for approved mods, but the
risk is yours. The recommended alternative is your own gameplay clips dropped into a
mod folder, which the editor prefers over images.

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
