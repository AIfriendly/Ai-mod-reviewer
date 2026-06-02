"""Editing stage. Submodules import heavy deps (moviepy) lazily, so light
helpers like `lower_third` (Pillow only) can be imported on their own.

Use `from skyrim_reviewer.edit.assemble import assemble_video`.
"""
