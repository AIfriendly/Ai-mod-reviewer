"""Export a 'narration kit' so the F5 voiceover can be generated on a free GPU
(Kaggle/Colab), then brought back for fast local assembly.

The kit is a folder + zip containing:
  - manifest.json : [{segment_id, text}, ...] for every spoken segment
  - reference.wav : your cloned-voice reference clip
  - f5_narrate.ipynb : the notebook that runs F5 on the GPU and zips the audio

Workflow: export here -> run the notebook on Kaggle -> download <slug>_audio.zip ->
drop the wavs in work/narration/ -> assemble with `provider: prerecorded` (fast, CPU).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def export_narration_kit(project, ref_audio: str = "voices/clone/ref_primary.wav",
                         ref_text: str = "") -> str:
    """Write the narration kit for a project; return the kit folder path."""
    slug = project.slug
    kit = Path("output") / f"{slug}_narration_kit"
    kit.mkdir(parents=True, exist_ok=True)

    segments = [{"segment_id": s.segment_id, "text": s.narration.strip()}
                for s in project.script.segments if s.narration.strip()]
    manifest = {"slug": slug, "ref_text": ref_text, "segments": segments}
    (kit / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ref = Path(ref_audio)
    if ref.exists():
        shutil.copyfile(ref, kit / "reference.wav")

    nb = ROOT / "kaggle" / "f5_narrate.ipynb"
    if nb.exists():
        shutil.copyfile(nb, kit / "f5_narrate.ipynb")

    # Zip for easy upload to Kaggle as a dataset.
    shutil.make_archive(str(kit), "zip", root_dir=str(kit))
    return str(kit)
