"""Runs ON Kaggle's GPU (pushed automatically by the pipeline).

Reads the narration kit dataset (manifest.json + reference.wav), generates one wav
per segment in the cloned voice with F5-TTS, and writes them to /kaggle/working.

IMPORTANT: we install F5-TTS WITHOUT pulling a new torch — Kaggle's image already
ships a CUDA build matched to its T4/P100 GPU, and letting pip replace it causes
`CUDA error: no kernel image is available for execution on the device`.
"""
import glob
import json
import os
import subprocess
import sys


def pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


# F5 itself, but keep Kaggle's GPU-matched torch/torchaudio (so --no-deps), then add
# F5's runtime deps explicitly (none of which bundle CUDA kernels).
pip("--no-deps", "f5-tts")
pip("x-transformers>=1.31.14", "vocos", "ema-pytorch>=0.5.2", "cached_path", "jieba",
    "pypinyin", "torchdiffeq", "num2words", "accelerate>=0.33.0", "datasets",
    "soundfile", "librosa", "transformers", "unidecode", "tomli", "pydub",
    "safetensors", "transformers-stream-generator", "hydra-core>=1.3.0")

import torch  # noqa: E402
print("CUDA available:", torch.cuda.is_available(),
      "| device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
      flush=True)

manifest_path = next(iter(glob.glob("/kaggle/input/**/manifest.json", recursive=True)))
kit = os.path.dirname(manifest_path)
manifest = json.load(open(manifest_path))
ref = os.path.join(kit, "reference.wav")
ref_text = manifest.get("ref_text", "") or ""
nfe = int(manifest.get("nfe_step", 32))

from f5_tts.api import F5TTS  # noqa: E402
tts = F5TTS(model="F5TTS_v1_Base")

os.makedirs("/kaggle/working", exist_ok=True)
for seg in manifest["segments"]:
    out = f"/kaggle/working/{seg['segment_id']}.wav"
    tts.infer(ref_file=ref, ref_text=ref_text, gen_text=seg["text"],
              file_wave=out, nfe_step=nfe, remove_silence=True)
    print("done", seg["segment_id"], flush=True)
print("ALL_SEGMENTS_DONE", flush=True)
