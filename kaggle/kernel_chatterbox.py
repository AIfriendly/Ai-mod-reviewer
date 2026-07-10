"""Runs ON Kaggle's GPU (pushed automatically by the pipeline).

Reads the narration kit dataset (manifest.json + reference.wav), generates one wav
per segment in the cloned voice with Chatterbox (Resemble AI, MIT), and writes them
to /kaggle/working. Chatterbox's cloning needs only the reference clip itself (no
transcript, unlike F5) — `generate(text, audio_prompt_path=ref)`.

GPU note: Kaggle assigns either a Tesla P100 (sm_60) or T4 (sm_75). Recent PyTorch
wheels dropped Pascal/P100 support ("CUDA error: no kernel image is available for
execution on the device") — the same issue the F5 kernel works around. We install
torch 2.4.1+cu121 (covers sm_60..sm_90, i.e. both P100 and T4) before chatterbox-tts,
constrained to that torch so its own dependency resolution can't replace it. If
chatterbox-tts turns out to need a newer torch than this, the install below will fail
with an explicit version-conflict message (not a silent breakage) — bump the pin here
if a real run shows that.
"""
import glob
import json
import os
import subprocess
import sys


def pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


pip("torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1",
    "--index-url", "https://download.pytorch.org/whl/cu121")
with open("/kaggle/working/constraints.txt", "w") as fh:
    fh.write("torch==2.4.1\ntorchvision==0.19.1\ntorchaudio==2.4.1\n")
pip("-c", "/kaggle/working/constraints.txt", "chatterbox-tts")

import torch  # noqa: E402
cap = torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None
print("CUDA:", torch.cuda.is_available(), "| torch", torch.__version__,
      "| device", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
      "| capability", cap, flush=True)

manifest_path = next(iter(glob.glob("/kaggle/input/**/manifest.json", recursive=True)))
kit = os.path.dirname(manifest_path)
manifest = json.load(open(manifest_path))
ref = os.path.join(kit, "reference.wav")

import torchaudio as ta  # noqa: E402
from chatterbox.tts_turbo import ChatterboxTurboTTS  # noqa: E402

device = "cuda" if torch.cuda.is_available() else "cpu"
model = ChatterboxTurboTTS.from_pretrained(device=device)

os.makedirs("/kaggle/working", exist_ok=True)
for seg in manifest["segments"]:
    out = f"/kaggle/working/{seg['segment_id']}.wav"
    wav = model.generate(seg["text"], audio_prompt_path=ref)
    ta.save(out, wav, model.sr)
    print("done", seg["segment_id"], flush=True)
print("ALL_SEGMENTS_DONE", flush=True)
