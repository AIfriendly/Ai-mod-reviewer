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


def run_kaggle_f5(segments: list[tuple[str, str]], ref_audio: str, ref_text: str,
                  nfe_step: int, out_dir: Path, timeout: int = 2400,
                  poll: int = 20, cleanup: bool = True) -> Path:
    """Generate <segment_id>.wav for each (segment_id, text) on Kaggle's GPU and
    download them into out_dir. Returns out_dir.

    On success the per-run dataset + kernel are deleted from your Kaggle account so
    they don't accumulate (cleanup=True). On failure they're kept so the log is
    inspectable. Local temp folders are always removed.
    """
    api, user = _auth()
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    slug = f"skyrim-f5-{tag}"
    kid = f"{user}/{slug}-run"
    ds_dir = out_dir / f"_kaggle_ds_{tag}"
    k_dir = out_dir / f"_kaggle_kernel_{tag}"

    try:
        # 1) Build + push the dataset (manifest + reference).
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

        # 2) Build + push the GPU kernel that runs F5 against that dataset.
        k_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KERNEL_SRC, k_dir / "kernel_f5.py")
        json.dump({"id": kid, "title": f"{slug}-run",
                   "code_file": "kernel_f5.py", "language": "python",
                   "kernel_type": "script", "is_private": True,
                   "enable_gpu": True, "enable_internet": True,
                   "dataset_sources": [f"{user}/{slug}"],
                   "competition_sources": [], "kernel_sources": []},
                  open(k_dir / "kernel-metadata.json", "w"))
        api.kernels_push(str(k_dir))

        # 3) Poll until the kernel finishes.
        deadline = time.time() + timeout
        status = "queued"
        while time.time() < deadline:
            time.sleep(poll)
            try:
                resp = api.kernels_status(kid)
                status = (resp.get("status") if isinstance(resp, dict)
                          else getattr(resp, "status", "")) or ""
                # Status is like "KernelWorkerStatus.RUNNING" — match on substring.
                status = str(status).lower()
            except Exception:
                continue
            if any(s in status for s in ("complete", "error", "cancel")):
                break
        if "complete" not in status:
            raise RuntimeError(f"Kaggle kernel did not complete (status={status}). "
                               f"Check https://www.kaggle.com/{kid}")

        # 4) Download outputs (the wavs) into out_dir.
        api.kernels_output(kid, path=str(out_dir), quiet=True)
        for sid, _ in segments:           # flatten any nested output
            found = next(iter(out_dir.rglob(f"{sid}.wav")), None)
            if found and found.parent != out_dir:
                shutil.move(str(found), str(out_dir / f"{sid}.wav"))

        if cleanup:                       # tidy the account on success
            _delete_remote(api, user, slug)
        return out_dir
    finally:
        # Local scratch always goes, plus the Kaggle output log file.
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
        segments = [(s.segment_id, s.narration.strip())
                    for s in script.segments if s.narration.strip()]
        print(f"      Offloading {len(segments)} segments to Kaggle GPU (F5)...")
        run_kaggle_f5(segments, self.ref_audio, self.ref_text, self.nfe_step,
                      out_dir, timeout=self.timeout)
        try:
            from ..config import voice_config
            do_enhance = voice_config().get("enhance", True)
        except Exception:
            do_enhance = True
        for s in script.segments:
            wav = out_dir / f"{s.segment_id}.wav"
            if wav.exists():
                if do_enhance:           # close-mic mastering, same as other providers
                    from .enhance import enhance_file
                    enhance_file(wav)
                s.audio_path = str(wav)
                s.audio_seconds = _audio_duration(wav)
        return script
