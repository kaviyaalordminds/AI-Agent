"""Shared capability-status shape for every generation provider family
(audio, transcription, image, video, voice) plus AI/Obsidian/Storage/
Deployment. This is exactly what GET /api/system/capabilities reports per
category — real, current status, never a guess and never faked as
"working" when it isn't.
"""
from dataclasses import dataclass
from typing import Literal


@dataclass
class CapabilityStatus:
    available: bool
    provider: str
    mode: Literal["local", "production"]
    reason: str
