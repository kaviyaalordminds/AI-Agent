import base64
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CreateVoiceCloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sample_audio_base64: str = Field(
        min_length=1,
        max_length=40_000_000,  # ~30MB decoded; storage.write() enforces the real MAX_UPLOAD_FILE_SIZE_MB limit
        description="Base64-encoded voice sample to clone.",
    )
    consent_confirmed: bool = Field(
        description="Must be true — explicit confirmation the caller has permission to clone this voice."
    )

    @field_validator("sample_audio_base64")
    @classmethod
    def _validate_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("sample_audio_base64 must be valid base64-encoded audio data.") from exc
        return value


class VoiceProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    created_at: datetime
    # provider_ref is deliberately never exposed here — it's the vendor's
    # internal voice ID, not something the frontend needs (see
    # app/models/voice_profile.py).

    model_config = {"from_attributes": True}
