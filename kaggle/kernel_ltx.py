"""Runs ON Kaggle's GPU (pushed automatically by the pipeline).

Reads an image-to-video kit (manifest.json + one input image per shot) and turns each
still mod screenshot into a short MOTION clip with LTX-Video (Lightricks, open weights),
writing one <shot_id>.mp4 to /kaggle/working. The pipeline then stitches these live
clips into the video in place of Ken Burns pans (falling back to Ken Burns for any shot
whose clip didn't come back).

GPU note: Kaggle assigns a Tesla P100 (sm_60) or T4 (sm_75). Its default PyTorch is too
new and dropped Pascal/P100 support ("CUDA error: no kernel image is available...").
We install torch 2.4.1+cu121 (covers sm_60..sm_90), then a diffusers new enough to ship
LTXImageToVideoPipeline. T4/P100 have weak bf16, so we run fp16 there (bf16 only on
Ampere+), with CPU offload + VAE tiling to fit 16 GB.
"""
import glob
import json
import os
import subprocess
import sys


def pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


# Torch build compatible with both P100 (sm_60) and T4 (sm_75); pin the stack so the
# diffusers install below can't pull an incompatible torch.
pip("torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1",
    "--index-url", "https://download.pytorch.org/whl/cu121")
with open("/kaggle/working/constraints.txt", "w") as fh:
    fh.write("torch==2.4.1\ntorchvision==0.19.1\ntorchaudio==2.4.1\n")
pip("-c", "/kaggle/working/constraints.txt",
    "diffusers>=0.32.0", "transformers>=4.44", "accelerate", "sentencepiece",
    "imageio", "imageio-ffmpeg")

import torch  # noqa: E402

cap = torch.cuda.get_device_capability(0) if torch.cuda.is_available() else (0, 0)
# bf16 only pays off on Ampere+ (sm_80); T4/P100 are far happier on fp16.
dtype = torch.bfloat16 if cap[0] >= 8 else torch.float16
print("CUDA:", torch.cuda.is_available(), "| torch", torch.__version__,
      "| device", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
      "| capability", cap, "| dtype", dtype, flush=True)

manifest_path = next(iter(glob.glob("/kaggle/input/**/manifest.json", recursive=True)))
kit = os.path.dirname(manifest_path)
manifest = json.load(open(manifest_path))
W = int(manifest.get("width", 768))
H = int(manifest.get("height", 512))
fps = int(manifest.get("fps", 24))
num_frames = int(manifest.get("num_frames", 97))     # ~4s @ 24fps; must be 8k+1
steps = int(manifest.get("steps", 30))
neg = manifest.get("negative_prompt",
                   "worst quality, blurry, jittery, distorted, warped text, flicker")

# LTX is picky: spatial dims must be divisible by 32, frame count must be 8*k + 1.
W -= W % 32
H -= H % 32
if (num_frames - 1) % 8 != 0:
    num_frames = ((num_frames - 1) // 8) * 8 + 1

from diffusers import LTXImageToVideoPipeline  # noqa: E402
from diffusers.utils import export_to_video, load_image  # noqa: E402

pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=dtype)
pipe.enable_model_cpu_offload()          # stream weights through the 16 GB card
try:
    pipe.vae.enable_tiling()             # decode the latent video in tiles to save VRAM
except Exception:
    pass

os.makedirs("/kaggle/working", exist_ok=True)
done = 0
for shot in manifest["shots"]:
    sid = shot["shot_id"]
    out = f"/kaggle/working/{sid}.mp4"
    if os.path.exists(out):
        done += 1
        print("skip (exists)", sid, flush=True)
        continue
    img_path = os.path.join(kit, shot["image"])
    prompt = shot.get("prompt") or ("Cinematic slow camera move over a fantasy game "
                                    "scene, gentle parallax, subtle ambient motion.")
    try:
        image = load_image(img_path)
        result = pipe(image=image, prompt=prompt, negative_prompt=neg,
                      width=W, height=H, num_frames=num_frames,
                      num_inference_steps=steps,
                      generator=torch.Generator().manual_seed(int(shot.get("seed", 0))))
        export_to_video(result.frames[0], out, fps=fps)
        done += 1
        print("done", sid, flush=True)
    except Exception as exc:                 # one bad shot must not kill the batch
        print("FAILED", sid, repr(exc), flush=True)
print(f"ALL_SHOTS_DONE {done}/{len(manifest['shots'])}", flush=True)
