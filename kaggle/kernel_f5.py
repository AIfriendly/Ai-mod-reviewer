"""Runs ON Kaggle's GPU (pushed automatically by the pipeline).

Reads the narration kit dataset (manifest.json + reference.wav), generates one wav
per segment in the cloned voice with F5-TTS, and writes them to /kaggle/working.

GPU note: Kaggle assigns either a Tesla P100 (sm_60) or T4 (sm_75). Its default
PyTorch is too new and dropped Pascal/P100 support, causing
`CUDA error: no kernel image is available for execution on the device`. We install
torch 2.4.1+cu121, whose binaries cover sm_60..sm_90 (P100 AND T4), then install
F5-TTS pinned to that torch so it isn't replaced.
"""
import glob
import json
import os
import subprocess
import sys


def pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


# A torch build compatible with both P100 (sm_60) and T4 (sm_75). torchvision must
# match (transformers' pipeline imports it; a mismatch -> "torchvision::nms" errors).
pip("torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1",
    "--index-url", "https://download.pytorch.org/whl/cu121")
# F5 + deps, but keep the torch stack we just installed.
with open("/kaggle/working/constraints.txt", "w") as fh:
    fh.write("torch==2.4.1\ntorchvision==0.19.1\ntorchaudio==2.4.1\n")
pip("-c", "/kaggle/working/constraints.txt", "f5-tts")

import torch  # noqa: E402
cap = torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None
print("CUDA:", torch.cuda.is_available(), "| torch", torch.__version__,
      "| device", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
      "| capability", cap, flush=True)

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
