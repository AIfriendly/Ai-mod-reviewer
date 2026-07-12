"""Chatterbox cloned-voice narration on Kaggle's FREE GPU, automatically.

Same zero-manual-click flow as the F5 path (kaggle_gpu.py): push the segment texts
+ your voice reference as a private Kaggle dataset, push a GPU kernel that runs
Chatterbox (Resemble AI, MIT-licensed — beat ElevenLabs 65.3% vs 24.5% in blind
listening tests), wait for it, download one wav per segment. Assembly then proceeds
normally (fast, CPU).

Chatterbox's cloning needs only the reference clip (no transcript, unlike F5), so
this provider is simpler than KaggleF5Provider — no ref_text / auto-transcription.

Setup: same Kaggle account + KAGGLE_API_TOKEN (or KAGGLE_USERNAME + KAGGLE_KEY) as
the F5 voice path. See kaggle_gpu.py's module docstring for account setup.

Use it: config/voice.yaml -> provider: chatterbox
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from .base import TTSProvider, _audio_duration
from .kaggle_gpu import (_auth, _concat_wavs, _delete_remote, _download_wavs,
                         _poll_kernel, _split_for_tts, _wait_dataset_ready)

ROOT = Path(__file__).resolve().parent.parent.parent
KERNEL_SRC = ROOT / "kaggle" / "kernel_chatterbox.py"


def run_kaggle_chatterbox(segments: list[tuple[str, str]], ref_audio: str,
                          out_dir: Path, timeout: int = 2400, poll: int = 20,
                          cleanup: bool = True, exaggeration: float = 0.5,
                          cfg_weight: float = 0.5) -> Path:
    """Generate <segment_id>.wav per (segment_id, text) on Kaggle's GPU, into out_dir.

    RESUMABLE: the job (dataset/kernel id) is recorded in out_dir/_kaggle_cb_job.json.
    If the local process is killed mid-run, the next call reattaches to the same
    kernel and just downloads its output. On full success the remote dataset +
    kernel are deleted (cleanup=True).
    """
    api, user = _auth()
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_ids = [sid for sid, _ in segments]
    job_file = out_dir / "_kaggle_cb_job.json"

    if job_file.exists():
        try:
            job = json.loads(job_file.read_text())
            slug, kid = job["slug"], job["kid"]
            got = _download_wavs(api, kid, out_dir, seg_ids)
            if not set(seg_ids) <= got:
                _poll_kernel(api, kid, timeout, poll)
                got = _download_wavs(api, kid, out_dir, seg_ids)
            if set(seg_ids) <= got:
                if cleanup:
                    _delete_remote(api, user, slug)
                    job_file.unlink(missing_ok=True)
                return out_dir
        except Exception:
            pass                                   # fall through to a fresh launch

    tag = uuid.uuid4().hex[:8]
    slug = f"skyrim-cb-{tag}"
    kid = f"{user}/{slug}-run"
    ds_dir = out_dir / f"_kaggle_ds_{tag}"
    k_dir = out_dir / f"_kaggle_kernel_{tag}"
    try:
        ds_dir.mkdir(parents=True, exist_ok=True)
        json.dump({"exaggeration": exaggeration, "cfg_weight": cfg_weight,
                   "segments": [{"segment_id": sid, "text": t} for sid, t in segments]},
                  open(ds_dir / "manifest.json", "w"), indent=2)
        shutil.copyfile(ref_audio, ds_dir / "reference.wav")
        json.dump({"title": slug, "id": f"{user}/{slug}",
                   "licenses": [{"name": "CC0-1.0"}]},
                  open(ds_dir / "dataset-metadata.json", "w"))
        api.dataset_create_new(str(ds_dir), public=False, quiet=True)
        _wait_dataset_ready(api, f"{user}/{slug}", timeout=300)

        k_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KERNEL_SRC, k_dir / "kernel_chatterbox.py")
        json.dump({"id": kid, "title": f"{slug}-run", "code_file": "kernel_chatterbox.py",
                   "language": "python", "kernel_type": "script", "is_private": True,
                   "enable_gpu": True, "enable_internet": True,
                   "dataset_sources": [f"{user}/{slug}"],
                   "competition_sources": [], "kernel_sources": []},
                  open(k_dir / "kernel-metadata.json", "w"))
        api.kernels_push(str(k_dir))
        job_file.write_text(json.dumps({"slug": slug, "kid": kid, "segments": seg_ids}))

        status = _poll_kernel(api, kid, timeout, poll)
        got = _download_wavs(api, kid, out_dir, seg_ids)
        if not (set(seg_ids) <= got):
            raise RuntimeError(
                f"Kaggle Chatterbox kernel incomplete (status={status}, got "
                f"{len(got)}/{len(seg_ids)} segments). Re-run to resume from "
                f"https://www.kaggle.com/{kid}")

        if cleanup:
            _delete_remote(api, user, slug)
            job_file.unlink(missing_ok=True)
        return out_dir
    finally:
        shutil.rmtree(ds_dir, ignore_errors=True)
        shutil.rmtree(k_dir, ignore_errors=True)
        (out_dir / f"{slug}-run.log").unlink(missing_ok=True)


class KaggleChatterboxProvider(TTSProvider):
    """Batch provider: renders all segments on Kaggle's GPU in one job."""

    def __init__(self, cfg: dict):
        self.ref_audio = cfg.get("ref_audio", "voices/clone/ref_primary.wav")
        self.timeout = int(cfg.get("timeout", 2400))
        self.exaggeration = float(cfg.get("exaggeration", 0.5))
        self.cfg_weight = float(cfg.get("cfg_weight", 0.5))

    def synth(self, text, out_path):  # pragma: no cover - batch only
        raise NotImplementedError(
            "KaggleChatterboxProvider renders the whole script at once.")

    def narrate_script(self, script, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        if not Path(self.ref_audio).exists():
            raise FileNotFoundError(
                f"Voice reference {self.ref_audio} missing — run `voice-prep` first.")
        from .pronounce import speakable
        # Chatterbox has no confirmed long-form cap, but chunk defensively (same as
        # F5) so one very long segment can't silently truncate or rush.
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
              f"({len(expanded)} chunks) to Kaggle GPU (Chatterbox)...")
        run_kaggle_chatterbox(expanded, self.ref_audio, out_dir, timeout=self.timeout,
                              exaggeration=self.exaggeration, cfg_weight=self.cfg_weight)
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
            for p in parts:
                if p != wav:
                    p.unlink(missing_ok=True)
            if do_enhance:
                from .enhance import enhance_file
                enhance_file(wav)
            s.audio_path = str(wav)
            s.audio_seconds = _audio_duration(wav)
        return script
