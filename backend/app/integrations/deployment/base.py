"""DeploymentProvider abstraction.

Same provider-abstraction pattern as everything else: application code
never talks to a hosting vendor's API directly. `get_deployment_provider()`
decides the concrete implementation from DEPLOYMENT_PROVIDER. Local
development gets a real, working "deploy" (zip + downloadable artifact,
via StorageProvider) with zero credentials required; production can
point at a real host once a vendor is wired up and configured.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.integrations.capability import CapabilityStatus


@dataclass
class DeploymentResult:
    provider: str
    storage_ref: str | None
    """Set for providers that produce a downloadable artifact (local)."""
    live_url: str | None
    """Set for providers that publish to a real, reachable URL (cloud)."""


class DeploymentProvider(ABC):
    @abstractmethod
    def capability(self) -> CapabilityStatus:
        raise NotImplementedError

    @abstractmethod
    def deploy(self, project_name: str, files: dict[str, bytes], owner_id: str) -> DeploymentResult:
        """`files` maps relative paths to their contents (e.g. a static
        site's index.html, style.css, ...). Raises
        GenerationProviderNotConfiguredError if unavailable, or
        GenerationProviderRequestError if the deployment itself fails —
        never fabricates a live URL."""
        raise NotImplementedError
