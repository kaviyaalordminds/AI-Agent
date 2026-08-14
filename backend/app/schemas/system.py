from typing import Literal

from pydantic import BaseModel


class CapabilityOut(BaseModel):
    available: bool
    provider: str
    mode: Literal["local", "production"]
    reason: str


class CapabilitiesOut(BaseModel):
    ai: CapabilityOut
    audio: CapabilityOut
    transcription: CapabilityOut
    voice: CapabilityOut
    image: CapabilityOut
    video: CapabilityOut
    documents: CapabilityOut
    obsidian: CapabilityOut
    storage: CapabilityOut
    deployment: CapabilityOut


class ComponentHealthOut(BaseModel):
    status: Literal["ok", "degraded", "down"]
    detail: str


class ProvidersHealthOut(BaseModel):
    database: ComponentHealthOut
    ai_provider: ComponentHealthOut
    obsidian: ComponentHealthOut
    storage: ComponentHealthOut
    job_queue: ComponentHealthOut
