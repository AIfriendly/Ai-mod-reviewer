"""AI-assisted Skyrim mod review video generator.

Pipeline stages (see skyrim_reviewer.pipeline):
  1. research  -> find & rank the best mods (NexusMods API, AUP-compliant)
  2. script    -> write the narration (Claude API)
  3. assets    -> download permitted media + build attribution manifest
  4. voice     -> render narration with your (cloned) voice
  5. edit      -> assemble video (moviepy/ffmpeg, Ken Burns on stills, music bed)
  6. package   -> thumbnail + Remotion title cards + metadata
"""

__version__ = "0.1.0"
