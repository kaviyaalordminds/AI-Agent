import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DeploymentStatus(str, enum.Enum):
    draft = "draft"
    deploying = "deploying"
    active = "active"
    failed = "failed"
    stopped = "stopped"


class DeploymentEnvironment(str, enum.Enum):
    production = "production"
    staging = "staging"


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A first-class, trackable deployment record with a real lifecycle
    (draft -> deploying -> active/failed, plus stopped) — separate from
    Website's own single-shot deploy fields (Website.deployment_provider/
    deployment_storage_ref/deployment_live_url, still used unchanged by
    Website Studio's inline "Deploy" button, see app/api/websites/
    router.py) so a deployment can be created, redeployed, stopped, and
    deleted as its own object without touching the source website's
    generation state.

    A Website is the only real deployable source in this codebase (a
    generated static HTML/CSS/JS project) — "3D Website" is presented as
    a distinct deployment type in the UI (derived from
    Website.style == "3d"), not a second source model. Actually
    deploying (see app/api/deployments/router.py's POST /{id}/deploy)
    reuses the exact same DeploymentProvider Website Studio already
    uses (see app/integrations/deployment/) — no parallel provider
    architecture."""

    __tablename__ = "deployments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("websites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[DeploymentEnvironment] = mapped_column(
        Enum(DeploymentEnvironment, name="deployment_environment"),
        default=DeploymentEnvironment.production,
        nullable=False,
    )
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status"), default=DeploymentStatus.draft, nullable=False, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Set once a real deploy() call has run (e.g. "local"); None while draft."""
    live_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()
    website: Mapped["Website"] = relationship()
