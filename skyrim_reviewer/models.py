"""Typed data models passed between pipeline stages.

Everything is JSON-serialisable so each stage can be run independently and its
output cached on disk in the project's work/ directory.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class VideoFormat(str, Enum):
    category_list = "category_list"
    transformation = "transformation"
    weekly_roundup = "weekly_roundup"


class MediaAsset(BaseModel):
    """A single downloadable image/video belonging to a mod."""
    url: str
    kind: str = "image"           # image | video
    local_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class Mod(BaseModel):
    """A NexusMods mod selected for the video."""
    mod_id: int
    name: str
    summary: str = ""
    author: str = ""
    uploaded_by: str = ""
    category_id: Optional[int] = None
    version: str = ""
    endorsements: int = 0
    downloads: int = 0
    updated_at: Optional[datetime] = None
    page_url: str = ""
    picture_url: str = ""
    # Footage policy fields:
    allow_media_reuse: bool = False   # author's permission flag (see research/nexus.py)
    media: list[MediaAsset] = Field(default_factory=list)
    # Ranking
    score: float = 0.0

    def credit_line(self) -> str:
        who = self.uploaded_by or self.author or "Unknown author"
        return f'"{self.name}" by {who} — {self.page_url}'


class Segment(BaseModel):
    """One narrated beat of the video (hook, a mod, or the outro)."""
    segment_id: str               # e.g. "hook", "mod_01", "outro"
    kind: str                     # hook | intro | mod | outro
    title: str = ""               # on-screen / chapter title
    narration: str = ""           # what the TTS voice says
    target_seconds: float = 0.0   # planned duration
    mod_id: Optional[int] = None  # link back to the Mod, if kind == "mod"
    # Filled by later stages:
    audio_path: Optional[str] = None
    audio_seconds: Optional[float] = None
    clip_path: Optional[str] = None


class Script(BaseModel):
    """The full narration script for a video."""
    title: str
    format: VideoFormat
    hook_line: str = ""           # the one-line title-card hook
    description: str = ""         # YouTube description
    tags: list[str] = Field(default_factory=list)
    chapters: list[str] = Field(default_factory=list)  # "0:00 Intro" lines
    segments: list[Segment] = Field(default_factory=list)


class VideoProfile(BaseModel):
    target_minutes: int
    mods_per_video: int
    seconds_per_mod: int
    hook_seconds: int
    intro_seconds: int
    outro_seconds: int


class Project(BaseModel):
    """The whole job: ties config choices to the artefacts produced."""
    slug: str                      # filesystem-safe id, e.g. 2026-06-02-weapons
    category_id: str = ""          # which category bucket (for category_list)
    theme: str = ""                # for transformation videos
    format: VideoFormat = VideoFormat.category_list
    profile_name: str = "test"
    profile: VideoProfile
    created_at: datetime = Field(default_factory=datetime.utcnow)
    mods: list[Mod] = Field(default_factory=list)
    script: Optional[Script] = None
    workdir: str = ""              # work/<slug>/
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    next_topic: str = ""           # teased as the next upload (used in the description)
    gofile_url: Optional[str] = None  # shared folder with video + title + thumb + desc
