"""Run the F5 cloned-voice narration on Kaggle's FREE GPU, automatically.

No manual clicking: the pipeline pushes the segment texts + your voice reference as a
private Kaggle dataset, pushes a GPU kernel that runs F5-TTS, waits for it, and
downloads one wav per segment. Then assembly proceeds normally (fast, CPU).

Setup (once): create a free Kaggle account, phone-verify it (Settings — required to
enable GPU + internet on kernels), generate an API token (Settings -> API -> Create
New Token), and put these in .env:
    KAGGLE_USERNAME=...
    KAGGLE_KEY=...

Use it:  skyrim-reviewer make <cat> --script <spec> --voice kaggle
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path

from .base import TTSProvider, _audio_duration

ROOT = Path(__file__).resolve().parent.parent.parent
KERNEL_SRC = ROOT / "kaggle" / "kernel_f5.py"


def _sidecar_text(ref_audio: str) -> str:
    """Read the reference transcript from <ref_audio>.txt if present."""
    sc = Path(ref_audio).with_suffix(".txt")
    return sc.read_text(encoding="utf-8").strip() if sc.exists() else ""


def _auth():
    """Authenticate the Kaggle API. Supports the new KAGGLE_API_TOKEN (KGAT_…) and
    the classic KAGGLE_USERNAME + KAGGLE_KEY. Returns (api, username)."""
    from ..config import get_env
    token = get_env("KAGGLE_API_TOKEN")
    user = get_env("KAGGLE_USERNAME")
    key = get_env("KAGGLE_KEY")
    kdir = Path.home() / ".kaggle"
    kdir.mkdir(exist_ok=True)
    if token:
        at = kdir / "access_token"
        at.write_text(token)
        at.chmod(0o600)
        os.environ["KAGGLE_API_TOKEN"] = token
    elif user and key:
        cfg = kdir / "kaggle.json"
        cfg.write_text(json.dumps({"username": user, "key": key}))
        cfg.chmod(0o600)
    else:
        raise RuntimeError(
            "Kaggle GPU voice needs KAGGLE_API_TOKEN (or KAGGLE_USERNAME + "
            "KAGGLE_KEY) in .env (Kaggle -> Settings -> API -> Create New Token).")
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()
    username = user or getattr(api, "config_values", {}).get("username")
    if not username:
        try:
            username = api.get_config_value("username")
        except Exception:
            username = None
    if not username:
        raise RuntimeError("Could not determine your Kaggle username from the token.")
    return api, username


def _delete_remote(api, user: str, slug: str) -> None:
    """Best-effort removal of the per-run dataset + kernel from the Kaggle account."""
    try:
        api.kernels_delete(f"{user}/{slug}-run", no_confirm=True)
    except Exception:
        pass
    try:
        api.dataset_delete(user, slug, no_confirm=True)
    except Exception:
        pass


def _download_wavs(api, kid: str, out_dir: Path, seg_ids: list[str]) -> set[str]:
    """Download a kernel's output and return the set of segment ids whose wav landed.
    Works even when the status API is flaky — the output endpoint often still serves."""
    try:
        api.kernels_output(kid, path=str(out_dir), quiet=True)
    except Exception:
        return {sid for sid in seg_ids if (out_dir / f"{sid}.wav").exists()}
    got = set()
    for sid in seg_ids:
        found = next(iter(out_dir.rglob(f"{sid}.wav")), None)
        if found and found.parent != out_dir:
            shutil.move(str(found), str(out_dir / f"{sid}.wav"))
        if (out_dir / f"{sid}.wav").exists():
            got.add(sid)
    return got


def _poll_kernel(api, kid: str, timeout: int, poll: int) -> str:
    deadline = time.time() + timeout
    status = "queued"
    while time.time() < deadline:
        time.sleep(poll)
        try:
            resp = api.kernels_status(kid)
            status = str((resp.get("status") if isinstance(resp, dict)
                          else getattr(resp, "status", "")) or "").lower()
        except Exception:
            continue                      # status API hiccup — keep waiting
        if any(s in status for s in ("complete", "error", "cancel")):
            break
    return status


def run_kaggle_f5(segments: list[tuple[str, str]], ref_audio: str, ref_text: str,
                  nfe_step: int, out_dir: Path, timeout: int = 2400,
                  poll: int = 20, cleanup: bool = True) -> Path:
    """Generate <segment_id>.wav per (segment_id, text) on Kaggle's GPU, into out_dir.

    RESUMABLE: the job (dataset/kernel id) is recorded in out_dir/_kaggle_job.json. If
    the local process is killed mid-run, the next call reattaches to the same kernel
    and just downloads its output — no re-launch, no GPU re-run. On full success the
    remote dataset + kernel are deleted (cleanup=True).
    """
    api, user = _auth()
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_ids = [sid for sid, _ in segments]
    job_file = out_dir / "_kaggle_job.json"

    # --- Resume an in-flight/finished job if one is recorded for this project ---
    if job_file.exists():
        try:
            job = json.loads(job_file.read_text())
            slug, kid = job["slug"], job["kid"]
            got = _download_wavs(api, kid, out_dir, seg_ids)
            if not set(seg_ids) <= got:           # not all ready yet -> wait, retry
                _poll_kernel(api, kid, timeout, poll)
                got = _download_wavs(api, kid, out_dir, seg_ids)
            if set(seg_ids) <= got:
                if cleanup:
                    _delete_remote(api, user, slug)
                    job_file.unlink(missing_ok=True)
                return out_dir
        except Exception:
            pass                                   # fall through to a fresh launch

    # --- Fresh launch ---
    tag = uuid.uuid4().hex[:8]
    slug = f"skyrim-f5-{tag}"
    kid = f"{user}/{slug}-run"
    ds_dir = out_dir / f"_kaggle_ds_{tag}"
    k_dir = out_dir / f"_kaggle_kernel_{tag}"
    try:
        ds_dir.mkdir(parents=True, exist_ok=True)
        json.dump({"ref_text": ref_text, "nfe_step": nfe_step,
                   "segments": [{"segment_id": sid, "text": t} for sid, t in segments]},
                  open(ds_dir / "manifest.json", "w"), indent=2)
        shutil.copyfile(ref_audio, ds_dir / "reference.wav")
        json.dump({"title": slug, "id": f"{user}/{slug}",
                   "licenses": [{"name": "CC0-1.0"}]},
                  open(ds_dir / "dataset-metadata.json", "w"))
        api.dataset_create_new(str(ds_dir), public=False, quiet=True)
        _wait_dataset_ready(api, f"{user}/{slug}", timeout=300)

        k_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KERNEL_SRC, k_dir / "kernel_f5.py")
        json.dump({"id": kid, "title": f"{slug}-run", "code_file": "kernel_f5.py",
                   "language": "python", "kernel_type": "script", "is_private": True,
                   "enable_gpu": True, "enable_internet": True,
                   "dataset_sources": [f"{user}/{slug}"],
                   "competition_sources": [], "kernel_sources": []},
                  open(k_dir / "kernel-metadata.json", "w"))
        api.kernels_push(str(k_dir))
        # Record the job IMMEDIATELY so an idle-kill is recoverable on the next run.
        job_file.write_text(json.dumps({"slug": slug, "kid": kid, "segments": seg_ids}))

        status = _poll_kernel(api, kid, timeout, poll)
        got = _download_wavs(api, kid, out_dir, seg_ids)
        if not (set(seg_ids) <= got):
            raise RuntimeError(
                f"Kaggle kernel incomplete (status={status}, got {len(got)}/{len(seg_ids)} "
                f"segments). Re-run to resume from https://www.kaggle.com/{kid}")

        if cleanup:
            _delete_remote(api, user, slug)
            job_file.unlink(missing_ok=True)
        return out_dir
    finally:
        shutil.rmtree(ds_dir, ignore_errors=True)
        shutil.rmtree(k_dir, ignore_errors=True)
        (out_dir / f"{slug}-run.log").unlink(missing_ok=True)


def _wait_dataset_ready(api, dataset_id: str, timeout: int = 300):
    """Kaggle processes a new dataset asynchronously; wait until it's usable."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            api.dataset_status(dataset_id)
            return
        except Exception:
            time.sleep(10)


def _split_for_tts(text: str, max_words: int = 50) -> list[str]:
    """Sentence-aware split into ≤~max_words pieces so each F5 generation stays well
    under its ~30s output cap (longer calls truncate/rush). Falls back to hard word
    splits for any single over-long sentence."""
    import re
    sents = re.findall(r".+?[.!?](?=\s|$)", text.strip()) or [text.strip()]
    chunks: list[str] = []
    cur = ""
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if len(s.split()) > max_words:               # very long sentence -> hard split
            if cur:
                chunks.append(cur); cur = ""
            words = s.split()
            for i in range(0, len(words), max_words):
                chunks.append(" ".join(words[i:i + max_words]))
        elif cur and len((cur + " " + s).split()) > max_words:
            chunks.append(cur); cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        chunks.append(cur)
    return chunks or [text.strip()]


def _concat_wavs(parts: list[Path], out: Path) -> None:
    """Concatenate chunk wavs into one segment wav (ffmpeg concat filter)."""
    import subprocess
    from ..utils.ffmpeg import ffmpeg_path
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        return
    args = [ffmpeg_path(), "-y", "-v", "error"]
    for p in parts:
        args += ["-i", str(p)]
    fc = "".join(f"[{i}:a]" for i in range(len(parts))) + \
        f"concat=n={len(parts)}:v=0:a=1[a]"
    args += ["-filter_complex", fc, "-map", "[a]", str(out)]
    subprocess.run(args, check=True, capture_output=True, text=True)


class KaggleF5Provider(TTSProvider):
    """Batch provider: renders all segments on Kaggle's GPU in one job."""

    def __init__(self, cfg: dict):
        self.ref_audio = cfg.get("ref_audio", "voices/clone/ref_primary.wav")
        # If no ref_text, use a sidecar <ref>.txt transcript so the GPU job can skip
        # Whisper auto-transcription (faster, and avoids torchcodec audio-decoder deps).
        self.ref_text = cfg.get("ref_text", "") or _sidecar_text(self.ref_audio)
        self.nfe_step = int(cfg.get("nfe_step", 32))
        self.timeout = int(cfg.get("timeout", 2400))

    def synth(self, text, out_path):  # pragma: no cover - batch only
        raise NotImplementedError("KaggleF5Provider renders the whole script at once.")

    def narrate_script(self, script, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        if not Path(self.ref_audio).exists():
            raise FileNotFoundError(
                f"Voice reference {self.ref_audio} missing — run `voice-prep` first.")
        from .pronounce import speakable
        # Split each segment into short chunks: F5 truncates/rushes a single long
        # generation (~30s cap), so we synth ≤~50-word pieces and concatenate them.
        # speakable() also fixes pronunciation here (this path bypasses base.narrate).
        expanded: list[tuple[str, str]] = []
        seg_chunks: dict[str, list[str]] = {}
        for s in script.segments:
            t = (s.narration or "").strip()
            if not t:
                continue
            chunks = _split_for_tts(speakable(t))
            ids = [f"{s.segment_id}__{i:02d}" for i in range(len(chunks))]
            seg_chunks[s.segment_id] = ids
            expanded += list(zip(ids, chunks))
        print(f"      Offloading {len(seg_chunks)} segments "
              f"({len(expanded)} chunks) to Kaggle GPU (F5)...")
        run_kaggle_f5(expanded, self.ref_audio, self.ref_text, self.nfe_step,
                      out_dir, timeout=self.timeout)
        try:
            from ..config import voice_config
            do_enhance = voice_config().get("enhance", True)
        except Exception:
            do_enhance = True
        for s in script.segments:
            ids = seg_chunks.get(s.segment_id)
            if not ids:
                continue
            parts = [out_dir / f"{cid}.wav" for cid in ids
                     if (out_dir / f"{cid}.wav").exists()]
            if not parts:
                continue
            wav = out_dir / f"{s.segment_id}.wav"
            _concat_wavs(parts, wav)
            for p in parts:                          # tidy the chunk files
                if p != wav:
                    p.unlink(missing_ok=True)
            if do_enhance:               # close-mic mastering, same as other providers
                from .enhance import enhance_file
                enhance_file(wav)
            s.audio_path = str(wav)
            s.audio_seconds = _audio_duration(wav)
        return script
