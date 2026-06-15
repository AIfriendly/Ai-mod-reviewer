"""Turn the still mod screenshots into real MOTION clips on Kaggle's FREE GPU.

Mirrors the F5 voice harness (skyrim_reviewer/voice/kaggle_gpu.py): we push the chosen
mod images + a manifest as a private Kaggle dataset, push a GPU kernel that runs
LTX-Video image-to-video, wait for it, and download one <shot_id>.mp4 per image. The
renderer then stitches these live clips in place of Ken Burns pans, falling back to
Ken Burns for any image whose clip didn't come back — so a GPU hiccup never breaks a
render.

Clips are content-addressed (hash of the image bytes) and cached under work/<slug>/i2v/,
so re-renders reuse them and the same image shared across shots is only generated once.

Enable with `video.i2v: true` in config (and the same KAGGLE_* creds the voice path uses).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

# Reuse the battle-tested Kaggle plumbing from the voice harness.
from ..voice.kaggle_gpu import (KERNEL_SRC as _F5_KERNEL, _auth, _delete_remote,
                                _poll_kernel, _wait_dataset_ready)

ROOT = Path(__file__).resolve().parent.parent.parent
KERNEL_SRC = ROOT / "kaggle" / "kernel_ltx.py"
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def clip_id(image_path: str) -> str:
    """Stable content-addressed id for an image, so its motion clip caches across runs."""
    h = hashlib.md5()
    h.update(Path(image_path).read_bytes())
    return "shot_" + h.hexdigest()[:16]


def _download_clips(api, kid: str, out_dir: Path, ids: list[str]) -> set[str]:
    """Download a kernel's output; return the set of shot ids whose mp4 landed."""
    try:
        api.kernels_output(kid, path=str(out_dir), quiet=True)
    except Exception:
        return {sid for sid in ids if (out_dir / f"{sid}.mp4").exists()}
    got = set()
    for sid in ids:
        found = next(iter(out_dir.rglob(f"{sid}.mp4")), None)
        if found and found.parent != out_dir:
            shutil.move(str(found), str(out_dir / f"{sid}.mp4"))
        if (out_dir / f"{sid}.mp4").exists():
            got.add(sid)
    return got


def generate_i2v_clips(jobs: list[tuple[str, str, str]], out_dir: Path, *,
                       width: int = 768, height: int = 512, fps: int = 24,
                       num_frames: int = 97, steps: int = 30,
                       timeout: int = 9000, poll: int = 30,
                       cleanup: bool = True) -> dict[str, str]:
    """Generate one motion mp4 per (shot_id, image_path, prompt) on Kaggle's GPU.

    Returns {shot_id: clip_path} for every clip available (freshly generated, cached, or
    recovered from an in-flight job). RESUMABLE: the job is recorded in
    out_dir/_i2v_job.json, so an idle-kill mid-run reattaches and just downloads output.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # Cache hit: clips already present need no GPU at all.
    have = {sid: str(out_dir / f"{sid}.mp4")
            for sid, _, _ in jobs if (out_dir / f"{sid}.mp4").exists()}
    pending = [(sid, img, pr) for sid, img, pr in jobs if sid not in have]
    if not pending:
        return have

    api, user = _auth()
    ids = [sid for sid, _, _ in pending]
    job_file = out_dir / "_i2v_job.json"

    # --- Resume an in-flight/finished job recorded for this project ---
    if job_file.exists():
        try:
            job = json.loads(job_file.read_text())
            slug, kid = job["slug"], job["kid"]
            got = _download_clips(api, kid, out_dir, ids)
            if not set(ids) <= got:
                _poll_kernel(api, kid, timeout, poll)
                got = _download_clips(api, kid, out_dir, ids)
            if got:
                if set(ids) <= got and cleanup:
                    _delete_remote(api, user, slug)
                    job_file.unlink(missing_ok=True)
                have.update({sid: str(out_dir / f"{sid}.mp4") for sid in got})
                if set(ids) <= got:
                    return have
        except Exception:
            pass

    # --- Fresh launch ---
    tag = uuid.uuid4().hex[:8]
    slug = f"skyrim-ltx-{tag}"
    kid = f"{user}/{slug}-run"
    ds_dir = out_dir / f"_ds_{tag}"
    k_dir = out_dir / f"_k_{tag}"
    try:
        ds_dir.mkdir(parents=True, exist_ok=True)
        shots = []
        for n, (sid, img, prompt) in enumerate(pending):
            ext = Path(img).suffix.lower() if Path(img).suffix.lower() in _IMG_EXT else ".jpg"
            shutil.copyfile(img, ds_dir / f"{sid}{ext}")
            shots.append({"shot_id": sid, "image": f"{sid}{ext}",
                          "prompt": prompt, "seed": n + 1})
        json.dump({"width": width, "height": height, "fps": fps,
                   "num_frames": num_frames, "steps": steps, "shots": shots},
                  open(ds_dir / "manifest.json", "w"), indent=2)
        json.dump({"title": slug, "id": f"{user}/{slug}",
                   "licenses": [{"name": "CC0-1.0"}]},
                  open(ds_dir / "dataset-metadata.json", "w"))
        api.dataset_create_new(str(ds_dir), public=False, quiet=True)
        _wait_dataset_ready(api, f"{user}/{slug}", timeout=300)

        k_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KERNEL_SRC, k_dir / "kernel_ltx.py")
        json.dump({"id": kid, "title": f"{slug}-run", "code_file": "kernel_ltx.py",
                   "language": "python", "kernel_type": "script", "is_private": True,
                   "enable_gpu": True, "enable_internet": True,
                   "dataset_sources": [f"{user}/{slug}"],
                   "competition_sources": [], "kernel_sources": []},
                  open(k_dir / "kernel-metadata.json", "w"))
        api.kernels_push(str(k_dir))
        job_file.write_text(json.dumps({"slug": slug, "kid": kid, "shots": ids}))

        status = _poll_kernel(api, kid, timeout, poll)
        got = _download_clips(api, kid, out_dir, ids)
        have.update({sid: str(out_dir / f"{sid}.mp4") for sid in got})
        if cleanup and set(ids) <= got:
            _delete_remote(api, user, slug)
            job_file.unlink(missing_ok=True)
        elif not got:
            raise RuntimeError(
                f"Kaggle LTX kernel produced no clips (status={status}). "
                f"Re-run to resume from https://www.kaggle.com/{kid}")
        return have
    finally:
        shutil.rmtree(ds_dir, ignore_errors=True)
        shutil.rmtree(k_dir, ignore_errors=True)
        (out_dir / f"{slug}-run.log").unlink(missing_ok=True)


def _prompt_for(mod_name: str, category: str) -> str:
    """A conservative motion prompt: ambient life + a slow drift, no wild camera work
    (heavy motion warps UI/text in game screenshots)."""
    subj = (category or "fantasy").strip()
    return (f"Cinematic establishing shot of a {subj} scene from {mod_name or 'Skyrim'}, "
            f"slow subtle camera drift, gentle parallax, soft ambient motion in foliage, "
            f"water and light; stable, photorealistic, no text distortion.")


def plan_and_generate(project, work_dir: Path, cfg: dict) -> dict[str, str]:
    """Collect the mod images used in this video and generate a motion clip for each
    (capped by `i2v_max_clips`; 0 = no cap / maximise coverage). Returns
    {image_local_path: clip_path} for clips that came back. On any failure returns {} so
    the renderer cleanly falls back to Ken Burns for everything."""
    cap = int(cfg.get("i2v_max_clips", 0) or 0)
    category = ""
    try:
        from ..config import channel_config
        category = channel_config()["channel"].get("game_domain", "")
    except Exception:
        pass

    seen: dict[str, tuple[str, str]] = {}     # clip_id -> (image_path, prompt)
    order: list[str] = []                      # image paths, in first-seen order
    img_to_sid: dict[str, str] = {}
    for mod in project.mods:
        for a in (mod.media or []):
            p = a.local_path
            if not (p and Path(p).suffix.lower() in _IMG_EXT and Path(p).exists()):
                continue
            try:
                sid = clip_id(p)
            except Exception:
                continue
            img_to_sid[p] = sid
            if sid not in seen:
                seen[sid] = (p, _prompt_for(mod.name, category))
                order.append(p)
    if cap > 0:
        keep = {img_to_sid[p] for p in order[:cap]}
        seen = {sid: v for sid, v in seen.items() if sid in keep}

    if not seen:
        return {}
    jobs = [(sid, img, pr) for sid, (img, pr) in seen.items()]
    out_dir = Path(work_dir) / "i2v"
    print(f"      Generating {len(jobs)} I2V motion clip(s) on Kaggle GPU (LTX)...")
    t0 = time.time()
    try:
        clips_by_sid = generate_i2v_clips(
            jobs, out_dir,
            width=int(cfg.get("i2v_width", 768)), height=int(cfg.get("i2v_height", 512)),
            fps=int(cfg.get("i2v_fps", 24)),
            num_frames=int(cfg.get("i2v_frames", 97)),
            steps=int(cfg.get("i2v_steps", 30)))
    except Exception as exc:
        print(f"      I2V generation failed ({exc}); using Ken Burns.")
        return {}
    print(f"      Got {len(clips_by_sid)} clip(s) in {time.time() - t0:.0f}s.")
    # Map every image path that resolved to a clip.
    return {p: clips_by_sid[sid] for p, sid in img_to_sid.items() if sid in clips_by_sid}
