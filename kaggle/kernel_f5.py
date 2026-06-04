"""Runs ON Kaggle's GPU (pushed automatically by the pipeline).

Reads the narration kit dataset (manifest.json + reference.wav), generates one wav
per segment in the cloned voice with F5-TTS, and writes them to /kaggle/working so
the pipeline can download them via `kernels_output`.
"""
import glob
import json
import os
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "f5-tts", "soundfile"],
               check=True)

manifest_path = next(iter(glob.glob("/kaggle/input/**/manifest.json", recursive=True)))
kit = os.path.dirname(manifest_path)
manifest = json.load(open(manifest_path))
ref = os.path.join(kit, "reference.wav")
ref_text = manifest.get("ref_text", "") or ""
nfe = int(manifest.get("nfe_step", 32))

import torch  # noqa: E402
print("CUDA:", torch.cuda.is_available(),
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU", flush=True)

from f5_tts.api import F5TTS  # noqa: E402
tts = F5TTS(model="F5TTS_v1_Base")

os.makedirs("/kaggle/working", exist_ok=True)
for seg in manifest["segments"]:
    out = f"/kaggle/working/{seg['segment_id']}.wav"
    tts.infer(ref_file=ref, ref_text=ref_text, gen_text=seg["text"],
              file_wave=out, nfe_step=nfe, remove_silence=True)
    print("done", seg["segment_id"], flush=True)
print("ALL_SEGMENTS_DONE", flush=True)
