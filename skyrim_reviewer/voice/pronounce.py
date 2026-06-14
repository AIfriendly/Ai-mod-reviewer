"""Make narration *speakable* for TTS without changing the on-screen text.

TTS engines (F5 included) mangle Skyrim/modding jargon: they try to pronounce
acronyms like "SKSE" or "ENB" as words, and trip over lore/author names. We rewrite
ONLY the text fed to the synthesiser — captions, SRT and the description keep the real
spelling. Conservative on purpose: only terms we're confident about, so we never make
a pronunciation worse.
"""
from __future__ import annotations

import re

# Acronyms/initialisms that should be spelled out letter-by-letter. Spaces make the
# engine read them as letters instead of attempting a (garbled) word.
_ACRONYMS = {
    "SKSE", "SKSE64", "ENB", "ENBs", "MCM", "DLC", "DLCs", "NPC", "NPCs", "UI", "AI",
    "FPS", "HD", "HDR", "LOD", "LODs", "ESP", "ESM", "ESL", "BSA", "DLL", "INI",
    "CBBE", "UNP", "BHUNP", "SMP", "HDT", "CTD", "CTDs", "FOMOD", "USSEP",
    "ELFX", "DYNDOLOD", "PBR", "GPU", "CPU", "RAM", "2D", "3D",
}

# Phonetic respellings for words a TTS reliably gets wrong (lore + common mod terms).
# Keep these high-confidence; lowercase keys match case-insensitively.
_PHONETIC = {
    "skse": "S K S E", "skyui": "Sky U I", "smim": "smimm",
    "daedric": "Daydric", "daedra": "Daydra", "dovahkiin": "Dohvah-keen",
    "dwemer": "Dwemmer", "dwemmer": "Dwemmer", "falmer": "Fal-mer",
    "phenderix": "Fenderiks", "taarengrav": "Tarren-grav", "falskaar": "Fal-skar",
    "wyrmstooth": "Wurms-tooth", "vigilant": "Vigilant", "moonpath": "Moon-path",
    "apocalypse": "Apocalypse", "summermyst": "Summer-mist", "ordinator": "Ordinator",
}

_4K = re.compile(r"\b([0-9])K\b")            # 4K -> "4 K"
_RES = re.compile(r"\b(\d{3,4})p\b", re.I)   # 1080p -> "1080 p"


def speakable(text: str) -> str:
    """Return a TTS-friendly version of `text` (display text is unchanged elsewhere)."""
    if not text:
        return text
    out = text
    # Spell out known acronyms (word-boundary, case-sensitive on the canonical form).
    for ac in sorted(_ACRONYMS, key=len, reverse=True):
        spaced = " ".join(ac.replace("64", "")) + (" sixty-four" if "64" in ac else "")
        # plural acronyms ("ENBs") -> "E N Bs"
        out = re.sub(rf"\b{re.escape(ac)}\b", spaced.strip(), out)
    out = _4K.sub(r"\1 K", out)
    out = _RES.sub(r"\1 p", out)
    # Phonetic respellings (case-insensitive, preserve nothing fancy — read aloud only).
    for word, say in _PHONETIC.items():
        out = re.sub(rf"\b{re.escape(word)}\b", say, out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out).strip()
