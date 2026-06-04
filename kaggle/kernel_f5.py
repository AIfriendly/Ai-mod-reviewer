"""Runs ON Kaggle's GPU (pushed automatically by the pipeline).

Reads the narration kit dataset (manifest.json + reference.wav), generates one wav
per segment in the cloned voice with F5-TTS, and writes them to /kaggle/working.

IMPORTANT: install F5-TTS with all its deps, but PIN torch/torchaudio to Kaggle's
preinstalled CUDA build (constraints file). Letting pip replace torch breaks the GPU
(`CUDA error: no kernel image is available for execution on the device`).
"""
import glob
import json
import os
import subprocess
import sys

import torch
import torchaudio

# Pin the GPU-matched torch so pip keeps it while installing F5's other deps.
con = "/kaggle/working/constraints.txt"
with open(con, "w") as fh:
    fh.write(f"torch=={torch.__version__}\ntorchaudio=={torchaudio.__version__}\n")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-c", con, "f5-tts"],
               check=True)

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
