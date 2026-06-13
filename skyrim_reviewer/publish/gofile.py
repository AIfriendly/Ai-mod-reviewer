"""Publish a finished video's artefacts to GoFile in one shared folder.

Bundles the MP4 + title + thumbnail + description into a single GoFile folder so
everything for an upload can be downloaded from one link. Uses GoFile's public API
with a guest account token (which lets multiple files share one folder).

Note: a GoFile guest link is accessible to anyone who has it — it's for your own
convenience, not private storage.
"""
from __future__ import annotations

from pathlib import Path

import httpx

_UA = "skyrim-reviewer/0.1"
_API = "https://api.gofile.io"


def upload_files(paths: list[str]) -> str | None:
    """Upload files into a single new GoFile folder. Returns the folder link."""
    files = [Path(p) for p in paths if p and Path(p).exists()]
    if not files:
        return None
    with httpx.Client(headers={"User-Agent": _UA}, timeout=300.0,
                      follow_redirects=True) as c:
        servers = [s["name"] for s in c.get(f"{_API}/servers").json()["data"]["servers"]]
        token = c.post(f"{_API}/accounts").json()["data"]["token"]
        auth = {"User-Agent": _UA, "Authorization": f"Bearer {token}"}

        def _upload(fp, folder_id):
            # Try servers in turn; GoFile returns 503 when a store node is down.
            last = None
            for server in servers:
                url = f"https://{server}.gofile.io/contents/uploadfile"
                data = {"folderId": folder_id} if folder_id else {}
                try:
                    with open(fp, "rb") as fh:
                        r = c.post(url, headers=auth, data=data,
                                   files={"file": (fp.name, fh)})
                    r.raise_for_status()
                    return r.json()["data"]
                except Exception as e:
                    last = e
                    continue
            raise last

        folder_id, page = None, None
        for fp in files:
            d = _upload(fp, folder_id)
            folder_id = folder_id or d.get("parentFolder") or d.get("parentFolderId")
            page = d.get("downloadPage") or page
        return page


def publish_project(project, include_thumbnails: bool = False) -> str | None:
    """Upload the project's video + title + description (+ subtitles) to one GoFile
    folder; returns the link.

    Thumbnails are NOT uploaded by default — they're delivered in chat. Pass
    include_thumbnails=True to also bundle the main thumbnail and A/B variants.
    """
    if not project.output_path or not Path(project.output_path).exists():
        return None
    out_dir = Path(project.output_path).parent
    slug = project.slug

    # Write a standalone title.txt so the title travels with the bundle.
    title_path = out_dir / f"{slug}.title.txt"
    title = project.script.title if project.script else slug
    title_path.write_text(title + "\n", encoding="utf-8")

    candidates = [
        project.output_path,                        # the video
        str(title_path),                            # the title
        str(out_dir / f"{slug}.description.txt"),    # the description
        str(out_dir / f"{slug}.srt"),               # subtitles (bonus)
    ]
    if include_thumbnails:
        candidates.append(project.thumbnail_path)
        candidates += list(getattr(project, "thumbnail_variants", []) or [])
    link = upload_files([p for p in candidates if p])
    project.gofile_url = link
    return link
