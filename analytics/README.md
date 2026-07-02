# Channel analytics

`skyrim-reviewer learn` pulls the channel's **public** YouTube stats (views, likes,
comments, upload dates) automatically via yt-dlp — no YouTube API key, nothing to
set up. It writes:

- `channel_stats.json` — raw per-video snapshot (git-ignored, regenerated each run)
- `config/performance_insights.yaml` — the distilled insights. `skyrim-reviewer
  ideas` samples winning categories more often, and the script writer receives the
  audience guidance in its prompt.

## Optional: richer owner-only metrics (CTR, retention)

Impressions, click-through rate, and retention are owner-only and can't be fetched
without OAuth. The supported path is a manual export:

1. YouTube Studio → Analytics → **Advanced mode**
2. Pick a table by *Content*, choose your date range
3. **Export current view** → CSV
4. Drop the `.csv` file(s) into this folder and re-run `skyrim-reviewer learn`

Any recognized columns (Impressions, Impressions click-through rate, Average
percentage viewed, Average view duration, Watch time, Subscribers) are merged onto
the matching videos by title and folded into the insights.
