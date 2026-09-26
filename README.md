# 🐉 AI Skyrim Mod Review Generator

Researches the best mods for a Nexus game, writes a narration script, narrates it in
**your cloned voice** (F5-TTS, runnable on a free Kaggle GPU), and edits a finished
YouTube video with **moviepy + ffmpeg** — a cinematic trailer-B-roll intro, documentary
Ken Burns on mod screenshots, royalty-free music — then renders a **Remotion** title
card + channel-style **thumbnail**, writes the **title + description**, and bundles
everything to a single **GoFile** link. All from one command.

```bash
skyrim-reviewer ideas                    # viral video ideas (modeled on top channels)
skyrim-reviewer make weapons             # full ~12-min video (default 'standard' profile)
skyrim-reviewer make weapons --game fallout4   # same pipeline, Fallout 4
```

Default cadence is built for **~2 uploads/week, 10–15 min each** (the `standard`
profile). `test` (5 min) and `full` (20 min) profiles are also available.

---

## Research-backed strategy (why it's built this way)

A deep research pass (Reddit r/skyrimmods + r/NewTubers, creator case studies,
2024–2026) drove these defaults. Full sourcing lives in the answers baked into
`config/channel.yaml`, but the short version:

| Decision | Finding |
|---|---|
| **Format = Hybrid** | Evergreen **"Best [category] Mods"** lists are the growth backbone (people search them for years); **"Transforming Skyrim into X"** videos are the viral spikes; **weekly roundups** decay fast — use sparingly. |
| **~20 min** | Long enough for 2–3 mid-roll ads. Structure: cold hook (no logo intro) → promise → 8–12 mods @ ~85–125s → save a banger for last → CTA. Start with **5-min test** videos to validate quality. |
| **Titles/thumbnails** | Channel-style titles (power word + number + year, e.g. `"The BEST Skyrim Weapon Mods in 2026! (8 You NEED)"`) and split-panel thumbnails with one accent keyword + big bold text, high contrast — modeled on top mod channels. Generate ideas with `skyrim-reviewer ideas`. |
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

**One-link delivery.** After each render, the video + title + thumbnail + description
(+ subtitles) are bundled into a single **GoFile** folder and the link is printed, so
you can grab everything for an upload from one place. Disable with `make --no-publish`;
re-bundle an existing render with `skyrim-reviewer publish <slug>`. Note: a GoFile
guest link is accessible to anyone who has it.

**Multiple games.** The whole pipeline is game-agnostic (it keys off the Nexus
`domain`). Target another game per video with `--game`:

```bash
skyrim-reviewer make weapons --game fallout4    # Fallout 4 mods (Pip-Boy green accent)
skyrim-reviewer research armor --game starfield
```

Supported games live in `config/games.yaml` (Nexus domain + Steam app id for trailer
B-roll + accent colour): Skyrim SE, Skyrim, Fallout 4, Starfield, Oblivion Remastered.
Category buckets in `channel.yaml` are Skyrim-tuned; other games work best with the
`weekly_roundup` format until their category ids are added.

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
research → script → assets → voice → edit → package → publish
  │         │         │        │       │       │         │
NexusMods  Claude or permitted your   moviepy Remotion   one GoFile
API ranks  YAML     media +    cloned ffmpeg  title card folder:
best mods  spec     gallery    voice  trailer + channel  video + title
(any game) writes   scrape     (F5 /  intro,  thumbnail  + thumbnail
           script              Kaggle Ken     + .srt     + description
                               GPU)   Burns,  + chapters
                                      music
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

# 3. Keys (.env) — NEXUS_API_KEY for research; ANTHROPIC_API_KEY only for the
#    automated script writer (the YAML-spec path needs neither); KAGGLE_API_TOKEN
#    for free-GPU voice; optional ElevenLabs/OpenAI voice keys.
cp .env.example .env

# 4. (Optional) Remotion title card + thumbnail (needs Node)
cd remotion && npm install && cd ..

# 5. (Optional) F5 cloned voice + royalty-free music
pip install f5-tts
skyrim-reviewer fetch-music
```

### Voice

Edit `config/voice.yaml` → `provider:` and fill the matching section. Options:
**`f5tts`** (*your cloned voice*, free/local), **`chatterbox`** (also a free/local
clone, no transcript needed), **`qwen`** (Qwen3-TTS, free/local ICL zero-shot
clone), `elevenlabs` (set `voice_id` or `ELEVENLABS_VOICE_ID`), `openai`,
`prerecorded` (drop `work/narration/<segment_id>.wav` files), or **`piper`**
(fast local voice, no cloning).

```bash
# F5-TTS cloned voice (default). Prepare a clean ≤15s reference of your voice:
pip install f5-tts
skyrim-reviewer voice-prep my_voice.wav        # -> voices/clone/ref_primary.wav
# config/voice.yaml -> provider: f5tts
```

A `<reference>.txt` sidecar (the reference's transcript) is used automatically if
present — it skips Whisper auto-transcription (faster, fewer deps). All narration is
**mastered** for a consistent, close-mic sound (`enhance: true` in `voice.yaml`):
a sub-bass high-pass + gentle −19 LUFS normalize. Tune the chain in
`skyrim_reviewer/voice/enhance.py`.

> **F5 is zero-shot** (clones from one ref clip + transcript at synth time). On CPU
> it's ~40–50× slower than realtime — fine for a test clip, not a 2-a-week schedule.

#### Free GPU narration via Kaggle (recommended for F5)

`--voice kaggle` offloads the F5 narration to Kaggle's **free GPU** automatically —
no manual clicking. It pushes your reference + segment texts as a private Kaggle
dataset, runs a GPU kernel, downloads one wav per segment, and (on success) deletes
the dataset + kernel so nothing accumulates. ~13-min total per video vs. ~1 hour on
CPU.

```bash
# One-time: phone-verify your Kaggle account (enables GPU + internet on kernels),
# then Settings -> API -> Create New Token. Put it in .env:
#   KAGGLE_API_TOKEN=KGAT_...        (or classic KAGGLE_USERNAME + KAGGLE_KEY)
skyrim-reviewer make weapons --voice kaggle
```

Manual alternative (no Kaggle automation): `skyrim-reviewer export-script weapons
--script <spec>` writes `output/<slug>_narration_kit.zip` (texts + reference +
`kaggle/f5_narrate.ipynb`); run it on any GPU notebook, drop the wavs in
`work/<slug>/narration/`, and assemble with `--voice prerecorded`.

For zero-cost CPU rendering with no clone, use **`piper`** instead.

```bash
# Fast local Piper voice (good for CPU testing / fallback)
pip install piper-tts
python -m piper.download_voices en_US-ryan-high --download-dir voices
# config/voice.yaml -> provider: piper  (model_path: voices/en_US-ryan-high.onnx)
```

**Qwen3-TTS** (`provider: qwen`) is another free/local zero-shot clone, open-weight
(Alibaba), no cloud account:

```bash
pip install -U qwen-tts torch soundfile
skyrim-reviewer voice-prep my_voice.wav        # -> voices/clone/ref_primary.wav
# config/voice.yaml -> provider: qwen
```

Without a transcript (`ref_text` empty and no `<reference>.txt` sidecar) it clones
from the reference audio alone (x-vector-only mode — no text needed, lower
fidelity than F5/Chatterbox with a transcript). Model weights (~5-10GB) download
once from HuggingFace on first use. Like F5, this is a 1.7B-param model — CPU
inference is slow with no GPU; set `device: cuda:0` in `voice.yaml` if you have one.

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
skyrim-reviewer ideas                      # viral video ideas + the make command for each
skyrim-reviewer categories                 # list category buckets (add --game fallout4)
skyrim-reviewer research weapons           # see the ranked mods (add --game ...)
skyrim-reviewer script weapons             # research + print the script (no render)
skyrim-reviewer make weapons               # full ~12-min video (default 'standard')
skyrim-reviewer make graphics --profile full        # 20-min deep-dive
skyrim-reviewer make armor --game fallout4          # another Nexus game
skyrim-reviewer make weapons --voice kaggle         # narrate on Kaggle's free GPU
skyrim-reviewer make weapons --no-publish           # skip the GoFile upload
skyrim-reviewer publish <slug>             # (re-)bundle a render to one GoFile link
skyrim-reviewer fetch-music                # download the default CC-BY music set
skyrim-reviewer voice-prep my_voice.wav    # prep an F5 voice reference
skyrim-reviewer approve <author|mod_id>    # permit a mod's media reuse
```

Key `make` flags: `--profile standard|test|full`, `--game <nexus_domain>`,
`--voice f5tts|kaggle|piper|elevenlabs|prerecorded`, `--fmt category_list|transformation|weekly_roundup`,
`--script <spec.yaml>`, `--no-publish`.

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
| `config/channel.yaml` | Niche, categories, video profiles (standard/test/full), ranking weights, branding, channel-style title templates, `intro_footage` |
| `config/voice.yaml` | TTS provider (f5tts/kaggle/piper/…), cloned-voice + `enhance` mastering |
| `config/games.yaml` | Multi-game registry: Nexus domain + Steam trailer app-id + accent + per-game categories (Skyrim SE, Skyrim, Fallout 4, Starfield, Oblivion Remastered) |
| `config/reference_channels.yaml` | Channels + viral formats the `ideas` generator models |
| `config/permissions.yaml` | Approved media reuse + `allow_gallery_scrape` / `gallery_max_images` |
| `.env` | API keys (NEXUS, optional ANTHROPIC, KAGGLE_API_TOKEN, voice keys) |

---

## Project layout

```
skyrim_reviewer/
  research/nexus.py       NexusMods API client + ranking (any game; AUP-compliant)
  research/gallery.py     Opt-in mod-gallery image scraper (more images per mod)
  research/footage.py     Official Steam trailer B-roll (cinematic intro)
  scripting/writer.py     Claude script generation (prompt caching + structured output)
  scripting/manual.py     Chat-authored YAML spec path (no API keys)
  assets/media.py         Permission-gated media download + credits manifest
  voice/                  Pluggable TTS: f5tts, kaggle_gpu (free GPU), piper,
                          elevenlabs, openai, prerecorded; enhance.py mastering
  edit/                   Trailer intro montage, Ken Burns, music, captions, assembly
  thumbnail/generate.py   Channel-style thumbnail (Remotion, PIL fallback)
  branding.py             Channel-style titles + YouTube description builder
  ideas.py                Viral video-idea generator
  publish/gofile.py       One-link delivery (video+title+thumb+description)
  pipeline.py / cli.py    Orchestration + CLI
remotion/                 Animated title card + thumbnail (React/Remotion)
kaggle/                   GPU narration kernel + notebook
config/                   channel / voice / games / reference_channels / permissions
```

---

## Status

End-to-end working. Two ways to run:

- **Chat-authored (no API keys):** use `--script <spec.yaml>` (see `examples/`).
  Only a voice is required to produce a finished video; placeholder slates cover
  any mod without permitted media.
- **Automated:** add `ANTHROPIC_API_KEY` (script writer) + `NEXUS_API_KEY`
  (research) to fetch and write everything programmatically.

For the cloned voice at production speed, set `KAGGLE_API_TOKEN` and use
`--voice kaggle` (free GPU). Configure the voice in `config/voice.yaml` and add
permission entries in `config/permissions.yaml` for any mod whose media you show.

**Known trade-offs (documented inline):** gallery scraping and trailer B-roll are
copyright/ToS-sensitive (opt-in, credited, short clips); F5 on CPU is impractically
slow (use the Kaggle GPU path); GoFile guest links are public.
