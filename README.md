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

### Your cloned voice

Edit `config/voice.yaml` → `provider: elevenlabs`, and set your cloned voice's
`voice_id` (or `ELEVENLABS_VOICE_ID` in `.env`). Other providers: `openai`,
`piper` (local/free), or `prerecorded` (drop `work/narration/<segment_id>.wav`
files you rendered yourself).

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
skyrim-reviewer make "the-witcher" --fmt transformation --theme "The Witcher"
```

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

This is a scaffold with working stage implementations. Before a real run you need:
`ANTHROPIC_API_KEY`, a `NEXUS_API_KEY`, a configured voice, and (for real footage)
permission entries. Without those, run `--skip-render` to exercise research +
scripting, or rely on placeholder slates for an end-to-end dry run.
