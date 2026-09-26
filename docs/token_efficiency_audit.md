# Token-efficiency audit

Scope note: skills and MCP servers are account-level (claude.ai settings), not
repo files — this session can only report on them, not delete them. The
"system prompt" is likewise controlled by the client, not by this repo; the
practical equivalent scoped to this project is the response-style section
added to `CLAUDE.md`, which Claude Code loads into every session here.

## 1. Skills/MCP audit (this session's active set)

MCP servers connected to this account/session:

| Server | Used by this project? | Recommendation |
|---|---|---|
| `github` | Yes — repo/PR workflow | Keep |
| `Claude_Code_Remote` | Yes — session/branch management | Keep |
| `Claude_Docs` | No reference in this repo | Keep only if you use it elsewhere; drop if idle |
| `Firecrawl` | No — research here goes through the NexusMods/Steam/yt-dlp APIs directly, no web scraping anywhere in `skyrim_reviewer/` | Delete unless used in another project |
| `Heygen` | No — this pipeline renders locally with moviepy/ffmpeg/Remotion, no HeyGen calls anywhere in `skyrim_reviewer/` | Delete unless used in another project |
| `HyperFrames_by_HeyGen` | No — same reason | Delete unless used in another project |

**Delete candidates: `Firecrawl`, `Heygen`, `HyperFrames_by_HeyGen`** — zero references in this codebase, all three add their tool descriptions to every session's starting context whether or not the session touches them.

Skills available in this session (built-in + installed) skew toward
Office-document generation (`pptx`, `docx`, `xlsx`, `pdf`), artifact/dataviz
authoring, and general Claude Code config (`update-config`,
`keybindings-help`, `fewer-permission-prompts`). None of that matches this
repo's actual workflow (Python CLI, YAML config, video rendering). Keep
`code-review`, `simplify`, `security-review`, `init`, `run`, `loop`, and
`claude-api` — they apply to any coding project. The document-format skills
(`pptx`/`docx`/`xlsx`/`pdf`) and Anthropic account skills (`morning`,
`import-memory`) are candidates to disable if you don't use them in other
projects on the same account — each loaded skill/MCP adds its description to
every session's starting context regardless of whether the session ends up
using it.

## 2. CLAUDE.md

Rewritten from scratch (none existed) at `/CLAUDE.md`, 118 lines: project
layout, coding conventions actually used in this codebase (Pydantic models,
Typer commands, httpx+tenacity, YAML config), how to verify a change (no test
suite exists), and the ToS/legal boundaries that must not be loosened
silently. No verbose prose, no restating the README.

## 3. Concise-by-default

Added as the first section of `CLAUDE.md` under "Response style" — this is
the mechanism Claude Code actually supports for a project-scoped default
(loaded into context every session on this repo). Account-wide system-prompt
edits aren't achievable from a repo session; that's a claude.ai/Claude Code
settings change on your end.

## 4. Repeatable tasks → shell scripts

Most of this pipeline is already scripted behind the `skyrim-reviewer` CLI
(research/script/make/publish/fetch-music/approve are all commands, not
ad-hoc AI asks). What's left running through AI/manual chat, from the commit
history (`Add X Vol.N spec`, `Record X in the no-repeat ledger`,
`Refresh performance insights`), and what to do about it:

| Repeatable task | Currently | Recommendation |
|---|---|---|
| Scaffolding a new `examples/*.yaml` spec (id, slug, category, mod list, empty narration beats) | Hand-authored per video, often via chat | Script it: a `tools/new_spec.py <category> <n-mods>` that emits the boilerplate structure (keys, date-stamped filename, mod IDs pulled from `research()`), leaving only narration text for a human/LLM to fill in. Mechanical scaffolding shouldn't cost model tokens. |
| Recording a finished video's mods in the no-repeat ledger | `pipeline.py`/`shorts.py` already call `history.record_video()` automatically when a video is made — but the ledger was still hand-edited via chat afterward at least twice (`9bc43eb`, `cee9613`), meaning those videos were rendered outside the automatic path (e.g. via the manual Kaggle-notebook route) | Write a `tools/record_history.py <slug>` that reads `work/<slug>/state.json` and calls `record_video()` directly, so an out-of-band render still gets a zero-token ledger update instead of an AI editing `history.json` by hand. |
| Checking YouTube/crosspost auth is valid | Already scripted (`youtube-check`, `crosspost-check`) | No change — good pattern, keep using it instead of asking the assistant to "check if YouTube is connected". |
| Re-running one pipeline stage after a config tweak (e.g. re-thumbnail after a branding change) | Ad hoc | `work/<slug>/state.json` already makes stages resumable — a thin `scripts/rerun_stage.sh <slug> <stage>` wrapping the existing resumable pipeline would avoid re-describing "just redo the thumbnail" in chat each time. |
| Verifying a spec renders end-to-end before a real run | Manual `make ... --profile test` invocation, typed fresh each time | Fine as a documented command (see `CLAUDE.md` verification section) — doesn't need a wrapper script, just don't re-derive the flags from scratch each session. |
| Fetching default royalty-free music set | Already scripted (`fetch-music`) | No change. |

Net: the pipeline itself is well-scripted already. The remaining token cost
is in per-video *content* decisions (which mods, narration wording) — those
are inherently creative and not worth scripting away. The two genuine gaps
(spec scaffolding, ledger bookkeeping) are the only items worth turning into
scripts.
