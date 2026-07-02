"""Channel performance feedback loop — NO YouTube API keys required.

`skyrim-reviewer learn` pulls the channel's PUBLIC stats (views, likes, comments,
upload dates) straight from YouTube via yt-dlp, joins each video to the category
that produced it (history.json title match), optionally merges richer owner-only
metrics (CTR, retention) from YouTube Studio CSV exports dropped in `analytics/`,
and distils everything into `config/performance_insights.yaml`.

Downstream consumers:
  * ideas.py      — weights category/format sampling toward what performs;
  * scripting     — the writer gets an AUDIENCE INSIGHTS block in its user prompt.

Private analytics (CTR, retention curves) can NOT be fetched without OAuth; the
supported path is manual: YouTube Studio -> Analytics -> Advanced mode -> Export
-> drop the CSV(s) into analytics/. Anything found there is merged automatically.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = ROOT / "config" / "performance_insights.yaml"
ANALYTICS_DIR = ROOT / "analytics"
SNAPSHOT_PATH = ANALYTICS_DIR / "channel_stats.json"

# Early views are inflated (subscriber notification spike); a video younger than
# this many days gets its views/day discounted proportionally.
_RAMP_DAYS = 5


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def fetch_channel_stats(handle: str) -> list[dict]:
    """Public per-video stats for a channel, via yt-dlp (no API key).

    Returns one dict per video: id, title, views, likes, comments, uploaded,
    age_days, duration_min, views_per_day (age-discounted).
    """
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("`pip install yt-dlp` to use the learn stage") from exc

    handle = handle.strip()
    if not handle.startswith(("http://", "https://")):
        handle = f"https://www.youtube.com/@{handle.lstrip('@')}"
    url = handle.split("?")[0].rstrip("/") + "/videos"

    flat = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(flat) as ydl:
        listing = ydl.extract_info(url, download=False)
    ids = [e["id"] for e in (listing.get("entries") or []) if e.get("id")]

    videos: list[dict] = []
    full = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(full) as ydl:
        for vid in ids:
            try:
                i = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}",
                                     download=False)
            except Exception:
                continue
            up = i.get("upload_date")
            age = ((date.today() - datetime.strptime(up, "%Y%m%d").date()).days
                   if up else None)
            views = i.get("view_count") or 0
            # Age-discounted velocity: brand-new videos ride the notification spike,
            # so scale their per-day figure down until they're _RAMP_DAYS old.
            eff_age = max(age or 1, 1)
            ramp = min(eff_age, _RAMP_DAYS) / _RAMP_DAYS
            videos.append({
                "id": vid, "title": i.get("title") or "",
                "views": views, "likes": i.get("like_count"),
                "comments": i.get("comment_count"),
                "uploaded": up, "age_days": age,
                "duration_min": round((i.get("duration") or 0) / 60, 1),
                "views_per_day": round(views / eff_age * ramp, 2),
            })
    return videos


def fetch_top_comments(video_id: str, limit: int = 20) -> list[str]:
    """Top viewer comments for one video (no API key). Best-effort; may be slow."""
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "getcomments": True,
                "extractor_args": {"youtube": {"max_comments": [f"{limit},all,0,0"]}}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}",
                                    download=False)
        return [c.get("text", "") for c in (info.get("comments") or [])[:limit]]
    except Exception:
        return []


def _infer_category(title: str) -> str:
    """Best-effort category from title keywords (configured categories). Needed
    because uploads are often hand-renamed, breaking exact ledger title matches."""
    try:
        from .config import channel_config
        cats = channel_config()["categories"]
    except Exception:
        return ""
    low = " " + _norm_title(title) + " "
    for c in cats:
        keys = [c["id"].replace("_", " ")] + [t.lower() for t in c.get("search_terms", [])]
        if any(f" {k} " in low or f" {k}s " in low for k in keys):
            return c["id"]
    return ""


def join_history(videos: list[dict]) -> None:
    """Attach the producing category/slug to each video. Exact normalized-title
    match against history.json first, then fuzzy (uploads get hand-renamed),
    then keyword inference from the configured categories. Mutates in place."""
    import difflib
    from .history import _load
    entries = [e for game in _load().values() for e in game]
    by_title = {_norm_title(e.get("title", "")): e for e in entries}
    for v in videos:
        norm = _norm_title(v["title"])
        hit = by_title.get(norm)
        if not hit and by_title:
            close = difflib.get_close_matches(norm, by_title, n=1, cutoff=0.65)
            hit = by_title[close[0]] if close else None
        if hit:
            v["category"] = hit.get("category", "")
            v["slug"] = hit.get("slug", "")
        else:
            v["category"] = _infer_category(v["title"])


def ingest_studio_csvs(videos: list[dict], directory: Path = ANALYTICS_DIR) -> int:
    """Merge YouTube Studio CSV exports (Advanced mode -> Export) onto `videos` by
    title. Lenient: scans every .csv, keeps only the columns we understand.
    Returns how many videos gained owner-only metrics."""
    aliases = {
        "impressions": "impressions",
        "impressions click-through rate (%)": "ctr_pct",
        "impressions click through rate (%)": "ctr_pct",
        "average percentage viewed (%)": "avg_pct_viewed",
        "average view duration": "avg_view_duration",
        "watch time (hours)": "watch_hours",
        "subscribers": "subs_gained",
    }
    by_title = {_norm_title(v["title"]): v for v in videos}
    merged: set[str] = set()
    for f in sorted(directory.glob("*.csv")) if directory.exists() else []:
        try:
            rows = list(csv.DictReader(f.open(encoding="utf-8-sig")))
        except Exception:
            continue
        for row in rows:
            low = {(k or "").strip().lower(): (val or "").strip()
                   for k, val in row.items()}
            title = low.get("video title") or low.get("content") or low.get("video")
            v = by_title.get(_norm_title(title or ""))
            if not v:
                continue
            for col, key in aliases.items():
                raw = low.get(col)
                if raw in (None, ""):
                    continue
                try:
                    v[key] = float(raw.replace(",", "").rstrip("%"))
                except ValueError:
                    v[key] = raw
            merged.add(v["id"])
    return len(merged)


def compute_insights(videos: list[dict]) -> dict:
    """Deterministic (no-LLM) distillation: per-category weights from views/day
    relative to the channel median, plus duration + title findings. The weights
    are what ideas.py samples with; the notes feed the script writer."""
    scored = [v for v in videos if v.get("views_per_day")]
    if not scored:
        return {}
    vpds = sorted(v["views_per_day"] for v in scored)
    median = vpds[len(vpds) // 2]

    by_cat: dict[str, list[dict]] = {}
    for v in scored:
        if v.get("category"):
            by_cat.setdefault(v["category"], []).append(v)
    weights = {}
    for cat, vs in by_cat.items():
        rel = (sum(x["views_per_day"] for x in vs) / len(vs)) / max(median, 0.01)
        weights[cat] = round(min(max(rel, 0.6), 1.6), 2)   # clamp 0.6x..1.6x

    best = max(scored, key=lambda v: v["views_per_day"])
    notes = [f"Top performer: \"{best['title']}\" "
             f"({best['views']} views, {best['views_per_day']}/day)."]
    for cat, w in sorted(weights.items(), key=lambda x: -x[1]):
        notes.append(f"Category '{cat}': weight {w} "
                     f"({len(by_cat[cat])} video(s)).")

    # Duration signal: compare above-median videos' lengths to the rest.
    hi = [v["duration_min"] for v in scored if v["views_per_day"] >= median]
    lo = [v["duration_min"] for v in scored if v["views_per_day"] < median]
    duration_hint = None
    if hi and lo and (sum(hi) / len(hi)) - (sum(lo) / len(lo)) >= 1.5:
        duration_hint = round(sum(hi) / len(hi))
        notes.append(f"Longer videos outperform: winners average "
                     f"~{duration_hint} min vs {sum(lo)/len(lo):.0f} min.")

    # CTR/retention findings when Studio CSVs were merged.
    ctrs = [(v["title"], v["ctr_pct"]) for v in scored if "ctr_pct" in v]
    if ctrs:
        top_t, top_c = max(ctrs, key=lambda x: x[1])
        notes.append(f"Best thumbnail/title CTR: {top_c:.1f}% on \"{top_t}\".")
    rets = [(v["title"], v["avg_pct_viewed"]) for v in scored if "avg_pct_viewed" in v]
    if rets:
        top_t, top_r = max(rets, key=lambda x: x[1])
        notes.append(f"Best retention: {top_r:.0f}% avg viewed on \"{top_t}\".")

    guidance = []
    if weights:
        ranked = sorted(weights.items(), key=lambda x: -x[1])
        guidance.append(
            "Audience data: topics ranked by performance — "
            + ", ".join(f"{c} ({w}x)" for c, w in ranked)
            + ". Lean the hook and title toward what the leaders promise.")
    if duration_hint:
        guidance.append(f"Longer videos hold this audience: target ~{duration_hint} "
                        f"minutes rather than the minimum.")
    if rets:
        guidance.append("Retention is measured — front-load the strongest mod "
                        "reveals; do not save all payoff for the end.")

    return {
        "updated": date.today().isoformat(),
        "videos_analyzed": len(scored),
        "median_views_per_day": median,
        "category_weights": weights,
        "duration_hint_minutes": duration_hint,
        "notes": notes,
        "script_guidance": guidance,
    }


def load_insights() -> dict:
    """The current insights, or {} when `learn` has never run. Never raises."""
    try:
        import yaml
        return yaml.safe_load(INSIGHTS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def learn(handle: str, with_comments: bool = False) -> dict:
    """Full feedback pass: fetch public stats -> join history -> merge Studio CSVs
    -> compute insights -> persist. Returns the insights dict."""
    import yaml
    videos = fetch_channel_stats(handle)
    join_history(videos)
    n_csv = ingest_studio_csvs(videos)
    if with_comments:
        for v in sorted(videos, key=lambda x: -(x.get("views") or 0))[:3]:
            v["top_comments"] = fetch_top_comments(v["id"])
    insights = compute_insights(videos)
    insights["channel"] = handle
    insights["studio_csv_videos"] = n_csv

    ANALYTICS_DIR.mkdir(exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(videos, indent=1), encoding="utf-8")
    INSIGHTS_PATH.write_text(
        "# Auto-generated by `skyrim-reviewer learn` — do not edit by hand.\n"
        + yaml.safe_dump(insights, sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    return insights
