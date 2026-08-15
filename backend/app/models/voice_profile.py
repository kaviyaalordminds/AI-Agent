import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VoiceProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's cloned voice (Audio Cloning feature). Scoped to the user
    who created it — never accessible cross-user, matching every other
    per-user resource in this app (Documents, GenerationJob, etc.). See
    app/integrations/generation/voice/base.py for consent requirements.

    `provider_ref` is the vendor's own voice ID (e.g. an ElevenLabs
    voice_id) — internal only, never returned by the API (see
    app/schemas/voice.py's VoiceProfileOut, which omits it entirely).
    This row's own `id` is what the frontend/API use to reference the
    voice everywhere, including when selecting it for Audio Generation."""

    __tablename__ = "voice_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    """Which VoiceProvider created this (e.g. "elevenlabs") — informational,
    also lets a future multi-vendor deployment route delete/synthesize
    calls to the right provider even if VOICE_PROVIDER changes later."""
    provider_ref: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship()
