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
  voice/                 Pluggable TTS: f5tts, kaggle_gpu, piper, elevenlabs, openai
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
  bypass the permission gate.
- Trailer B-roll (`research/footage.py`) and GoFile links are called out in
  the README as copyright/exposure risks — keep behavior opt-out-able, not
  silently expanded.
