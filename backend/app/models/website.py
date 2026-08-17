import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WebsiteStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Website(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An AI-drafted static website (Phase 8, Developer Studio): the
    user's description + page list is turned into real, complete HTML
    pages via Claude in one structured completion, each written through
    StorageProvider — same honesty contract as Document generation (the
    prompt is persisted even on failure, never a fabricated result — see
    app/websites/generator.py). "3D Website" is not a separate module:
    it's the style="3d" option on this same pipeline, which instructs
    Claude to include a real, working Three.js scene rather than faking
    3D content some other way. Deployment (a real downloadable zip today
    via LocalDeploymentProvider; a real live URL once Netlify/Vercel
    credentials are configured) is a separate step logged to History as
    its own 'deployment' entry, not folded into generation."""

    __tablename__ = "websites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[WebsiteStatus] = mapped_column(Enum(WebsiteStatus, name="website_status"), nullable=False)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    """[{"name": str, "path": str, "storage_ref": str, "size_bytes": int}, ...] — empty on failure."""

    deployment_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deployment_storage_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    deployment_live_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
