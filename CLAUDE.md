# AI Skyrim Mod Review Generator

Python CLI (`skyrim-reviewer`) that turns a Nexus mod category into a finished
YouTube video: research → script → assets → voice → edit → package → publish.
Entry point: `skyrim_reviewer/cli.py` (Typer app). Full pipeline orchestration
lives in `skyrim_reviewer/pipeline.py`.

## Response style (applies to all work in this repo)

Be concise by default:
- Answer first, explanation after. No filler, no restating the request.
- Only read/edit files required for the task — no speculative broad scans.
- For multi-file changes, outline the plan briefly before editing rather than
  narrating every step.
- Prefer running the project's own checks (see below) over hand-written debug
  output to verify a change.
- If a requested change turns out to be unnecessary given what you find in the
  code, say so and stop instead of doing it anyway.

## Project layout

```
skyrim_reviewer/
  research/nexus.py     NexusMods API client + ranking (any game, AUP-compliant)
  research/gallery.py   Opt-in gallery scraper (ToS-violating, off by default)
  research/footage.py   Steam trailer B-roll for the cinematic intro
  research/reference_scrape.py  Optional Firecrawl lookup for `ideas --live`
  scripting/writer.py   Claude-based script generation (needs ANTHROPIC_API_KEY)
  scripting/manual.py   Chat-authored YAML spec path (no API keys needed)
  scripting/autospec.py Automated idea -> spec generation
  assets/media.py       Permission-gated media download + credits manifest
  voice/                 Pluggable TTS: f5tts, chatterbox, qwen, kaggle_gpu, piper,
                          elevenlabs, openai
  edit/                  Trailer intro montage, Ken Burns, music, captions, assembly
  edit/tier_list.py     ranked_tier_list on-screen graphics: scorecard, best-for, tier board
  edit/encode_opts.py   ffmpeg codec/preset + video-config helpers (no moviepy import)
  thumbnail/generate.py Channel-style thumbnail (Remotion, PIL fallback)
  branding.py            Titles + YouTube description builder
  ideas.py               Viral video-idea generator
  publish/gofile.py      One-link delivery bundle
  qa.py                  Pre-render QA checks
  analytics.py           `learn` command: channel stats feedback loop
  pipeline.py / cli.py   Orchestration + CLI commands
remotion/                Animated title card + thumbnail (React/Remotion, Node)
kaggle/                  Free-GPU narration kernels + notebook
config/                  channel / voice / games / reference_channels / permissions YAML
                          channel.yaml -> tier_list: tiers + scorecard criteria for ranked_tier_list
examples/                Worked YAML specs (chat-authored, no-API-key path)
tools/                   One-off scripts (gallery fetch, YouTube OAuth)
```

Each pipeline stage writes `work/<slug>/state.json`, so stages are resumable —
don't assume a stage needs to re-run from scratch.

## Coding style

- Python 3.10+, `from __future__ import annotations` at the top of modules
  that use modern type-hint syntax (`str | None`, `list[str]`, etc.).
- Pydantic v2 `BaseModel` for anything passed between pipeline stages
  (`models.py`) — keep new cross-stage data typed and JSON-serialisable, not
  ad-hoc dicts.
- Typer for CLI commands (`cli.py`): one `@app.command()` function per verb,
  keyword options with `typer.Option(...)`, positional required args with
  `typer.Argument(...)`.
- Module docstrings explain *why* a file exists and its role in the pipeline,
  not a line-by-line description. Keep that pattern; don't add narrative
  comments inside function bodies unless a constraint is genuinely non-obvious
  (e.g. the `pil_compat.py` ANTIALIAS shim, the NexusMods ToS boundary in
  `gallery.py`).
- Config is YAML under `config/`, loaded via `config.py` with `${ENV_VAR}`
  expansion — don't hardcode values that belong in a channel/game/voice config
  file.
- Network calls (NexusMods, Kaggle, GoFile, YouTube) go through `httpx` with
  `tenacity` retry/backoff — follow that pattern for new integrations rather
  than raw `requests` or manual retry loops.
- Anthropic API usage is isolated to `scripting/writer.py`; the rest of the
  pipeline (and the `--script <spec.yaml>` path) must keep working with zero
  API keys except a voice provider.

## Environment / keys

`.env` (see `.env.example`): `NEXUS_API_KEY` (research), `ANTHROPIC_API_KEY`
(optional, automated script writer only), `KAGGLE_API_TOKEN` (free-GPU voice),
optional ElevenLabs/OpenAI voice keys, YouTube/Ayrshare credentials for
publishing, and `FIRECRAWL_API_KEY` (optional — `ideas --live` reference-channel
freshness layer; everything else works with it unset).

YouTube auth (`YOUTUBE_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN`):
- `tools/youtube_auth.py` catches an OAuth redirect on localhost, so it only
  works where the browser and the script are the same machine — never from a
  sandbox. `tools/youtube_auth_device.py` uses Google's device flow instead
  (no redirect; the user approves a short code on any device) and is the only
  option for a headless host.
- The device endpoint requires an OAuth client of type "TVs and Limited Input
  devices"; a Desktop-app client is rejected with "Invalid client type".
- Device flow permits only the `youtube` and `youtube.readonly` scopes.
  `videos.insert` and `thumbnails.set` accept `youtube`, but comment posting
  needs `youtube.force-ssl`, which that flow cannot grant.
- Until the Google Cloud project passes YouTube's compliance audit, every
  API-uploaded video is forced to `private` and `publishAt` scheduling won't
  fire. Don't treat that as a bug in the uploader.
- The account owns several channels, so `upload_video` takes `expect_channel`
  and aborts on a mismatch. Keep that guard.

## Research: finding the right mods

- Prefer NexusMods' own taxonomy over inferring content from titles. The v2
  GraphQL `mods` query returns a `tags { name }` field, and dedicated
  categories exist for most buckets ("Quests", "Magic - Spells & Enchantments").
  Regex classifiers over name/summary (`_is_quest`, `_is_new_land` in
  `autospec.py`) are a last resort for buckets Nexus doesn't separate — a
  regex pass once returned ZERO valid quest mods for a year that actually had
  dozens.
- "Best of <year>" means `createdAt` in that year. `discover_mods()` sorts by
  endorsements, which structurally cannot surface recent releases — a new mod
  has no endorsements yet. Sort by `createdAt DESC` and page until the results
  fall out of the year, then rank the survivors by endorsements.
- A mod updated this year is not a mod released this year; filter on
  `createdAt`, never `updatedAt`.
- Always filter out: `adultContent`, the `Translation` tag, non-Latin titles
  (the narration is English), mods already in `history.json` for that game
  domain, and anything without real media or a usable summary.

## Narration style

The templates in `autospec.py` (`_HOOKS_FIRST`, `_HOOKS_PART`, `_INTROS`,
`_OUTROS`, `_teaser`) follow the structure used by the established Skyrim
mod-showcase channels in `config/reference_channels.yaml`. Keep that shape
when editing them:

- **Open by naming what is actually in this video.** Greet the viewer, say
  specifically what this episode covers, then hand off to the first entry
  ("let's begin", "first off, let's take a look"). A generic "N of the best
  mods" promises nothing and makes every video sound identical — `_teaser`
  exists to name real entries from the list being built.
- **Per mod: name it, say what it is in one line, then get concrete.** The
  reference channels lead with specifics — counts of NPCs, voice lines or
  quests, named requirements, what changed versus vanilla. Concrete detail is
  what makes a segment worth watching; adjectives are not.
- **Close short and warm.** Hope they found something for their load order,
  credit the authors, one like/subscribe ask, sign off. Don't stack CTAs.
- **Second person, direct address.** "You" and "we", not "the player".

Two hard limits: take structure and rhythm only — never lines verbatim, and
never another channel's host persona or name. Every factual claim about a mod
comes from that mod's own Nexus page, never from a reference video and never
invented.

To study a channel, `yt-dlp` is rate-limited (HTTP 429) from the sandbox and
YouTube 401s Firecrawl on channel pages. What works: Firecrawl's `/v1/scrape`
endpoint (needs `FIRECRAWL_API_KEY`; the repo's `reference_scrape.py` only
calls `/v1/search`) against a transcript site with `waitFor` set, since those
pages render client-side. Verify the author field on the scraped page — search
results routinely surface other channels' videos. Don't commit the
transcripts.

## Video output constraints

- YouTube descriptions hard-cap at 5000 characters and the rest is silently
  dropped. `make_description` shrinks to fit — don't add unconditional
  sections to it. Timestamp+link lines run ~95 chars, so links only fit for
  roughly 50 mods; beyond that the pinned comment carries them.
- Qwen TTS speaks about 3.6 words/second, much faster than the hand-written
  `target_seconds` in a spec implies. Estimate runtime from narration word
  count, and hit a length target by writing more real detail mined from the
  mod's full Nexus description — never filler, never invented facts.
- On-screen cards (`edit/tier_list.py`) are full-frame RGBA overlays
  composited on top of each other. Two cards that both draw mid-frame WILL
  collide; give each a vertical band, or show them in separate time windows
  via `overlay=...:enable=`.
- Check rendered output by extracting frames (`ffmpeg -ss <t> -frames:v 1`)
  and actually looking at them. Layout bugs — overlapping cards, dropped
  items — do not show up in logs, exit codes, or QA.

## Long renders

- A full-length render takes hours. Start it as the background command
  itself; a `nohup ... &` inside a backgrounded call has been reaped
  mid-render, losing the run.
- Depth-parallax clips (`edit/parallax.py`) are cached by hash, so re-running
  a render reuses them. Re-render the final stage rather than rebuilding a
  project from scratch.
- Never delete files while a background job may still be writing them (the
  `ffmpeg2pass-*.log` files belong to an in-flight two-pass encode).
- `work/<slug>/ffsegs` and `work/<slug>/i2v` are regenerable intermediates and
  are where the disk goes; clearing them for a finished, delivered video is
  the safe way to make room. The `output/*.mp4` deliverables are not.
- `history.json` edits: make the precise change and read `git diff` before
  committing. A blanket dedupe script once silently dropped six unrelated
  entries.

## Verifying changes

There is no test suite or linter configured in this repo (no `pytest`,
`Makefile`, or CI config present). To verify a change:
- `skyrim-reviewer script <category> --script <spec.yaml>` — runs research
  through script generation without rendering, fastest smoke test.
- `skyrim-reviewer make <category> --profile test --script <spec.yaml>
  --no-publish` — full pipeline on the short (~5 min) profile, no upload.
- For pipeline-stage-only changes, prefer re-running just the affected stage
  against an existing `work/<slug>/` directory over a full re-render.
- `python -c "import skyrim_reviewer.cli"` as a minimal import/syntax check
  when you can't run the full CLI (e.g. missing API keys).

## Legal/ToS-sensitive areas — do not loosen without being asked

- `research/gallery.py` (`allow_gallery_scrape`) violates the NexusMods ToS by
  design; it's opt-in and documented as a risk the user accepts. Don't enable
  it by default or remove the warnings.
- `assets/media.py` only uses mod media that's in the permissions ledger
  (`config/permissions.yaml`) or falls back to a placeholder slate. Don't
  bypass the permission gate. Approving a batch asserts the user has real
  permission from those authors, so confirm it with them per batch — it is
  not implied by them asking for the video, and a previous batch's answer
  does not carry over to different mods.
- Trailer B-roll (`research/footage.py`) and GoFile links are called out in
  the README as copyright/exposure risks — keep behavior opt-out-able, not
  silently expanded.
