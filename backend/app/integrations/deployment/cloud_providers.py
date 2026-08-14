from app.integrations.capability import CapabilityStatus
from app.integrations.deployment.base import DeploymentProvider, DeploymentResult
from app.integrations.generation.errors import GenerationProviderNotConfiguredError


class NetlifyProvider(DeploymentProvider):
    """Architecture point for real Netlify deployments. Selected via
    DEPLOYMENT_PROVIDER=netlify; requires NETLIFY_API_TOKEN."""

    def __init__(self, api_token: str | None) -> None:
        self._api_token = api_token

    def capability(self) -> CapabilityStatus:
        if self._api_token:
            return CapabilityStatus(
                available=True, provider="netlify", mode="production", reason="Netlify API token configured."
            )
        return CapabilityStatus(
            available=False,
            provider="netlify",
            mode="production",
            reason="Set NETLIFY_API_TOKEN in the backend environment to enable Netlify deployments.",
        )

    def deploy(self, project_name: str, files: dict[str, bytes], owner_id: str) -> DeploymentResult:
        if not self._api_token:
            raise GenerationProviderNotConfiguredError(self.capability().reason)
        raise GenerationProviderNotConfiguredError(
            "Netlify deployment support is architected but not yet implemented in this "
            "deployment — the Netlify API client integration is a future addition."
        )


class VercelProvider(DeploymentProvider):
    """Architecture point for real Vercel deployments. Selected via
    DEPLOYMENT_PROVIDER=vercel; requires VERCEL_API_TOKEN."""

    def __init__(self, api_token: str | None) -> None:
        self._api_token = api_token

    def capability(self) -> CapabilityStatus:
        if self._api_token:
            return CapabilityStatus(
                available=True, provider="vercel", mode="production", reason="Vercel API token configured."
            )
        return CapabilityStatus(
            available=False,
            provider="vercel",
            mode="production",
            reason="Set VERCEL_API_TOKEN in the backend environment to enable Vercel deployments.",
        )

    def deploy(self, project_name: str, files: dict[str, bytes], owner_id: str) -> DeploymentResult:
        if not self._api_token:
            raise GenerationProviderNotConfiguredError(self.capability().reason)
        raise GenerationProviderNotConfiguredError(
            "Vercel deployment support is architected but not yet implemented in this "
            "deployment — the Vercel API client integration is a future addition."
        )
