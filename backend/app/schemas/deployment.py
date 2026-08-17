import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.deployment import DeploymentEnvironment, DeploymentStatus


class CreateDeploymentRequest(BaseModel):
    website_id: uuid.UUID
    name: str | None = Field(default=None, max_length=255, description="Defaults to the website's own name.")
    environment: Literal["production", "staging"] = "production"


class UpdateDeploymentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    environment: Literal["production", "staging"] | None = None


class DeploymentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None = None
    website_id: uuid.UUID
    website_name: str
    deployment_type: Literal["website", "website_3d"]
    """Derived from the source Website's style ("3d" -> website_3d) —
    not a separate stored source type, since a Website is the only
    real deployable source this codebase produces today."""
    name: str
    environment: DeploymentEnvironment
    status: DeploymentStatus
    provider: str | None
    live_url: str | None
    downloadable: bool
    error: str | None
    created_at: datetime
    updated_at: datetime
    deployed_at: datetime | None

    model_config = {"from_attributes": True}
