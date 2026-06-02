"""Pillow 10 compatibility shim for MoviePy 1.x.

MoviePy 1.x calls the deprecated ``PIL.Image.ANTIALIAS`` (and a few siblings) that
were removed in Pillow 10. Our requirements pin Pillow>=10, so import this module
before any MoviePy resize runs to restore the old constants.
"""
from PIL import Image

_aliases = {
    "ANTIALIAS": "LANCZOS",
    "BILINEAR": "BILINEAR",
    "BICUBIC": "BICUBIC",
    "NEAREST": "NEAREST",
}
for _old, _new in _aliases.items():
    if not hasattr(Image, _old) and hasattr(Image, "Resampling"):
        setattr(Image, _old, getattr(Image.Resampling, _new))
