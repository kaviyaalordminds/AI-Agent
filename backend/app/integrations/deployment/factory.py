from app.core.config import get_settings
from app.integrations.deployment.base import DeploymentProvider
from app.integrations.deployment.cloud_providers import NetlifyProvider, VercelProvider
from app.integrations.deployment.local_provider import LocalDeploymentProvider
from app.integrations.storage.factory import get_storage_provider


def get_deployment_provider() -> DeploymentProvider:
    settings = get_settings()
    if settings.deployment_provider == "local":
        return LocalDeploymentProvider(get_storage_provider())
    if settings.deployment_provider == "netlify":
        return NetlifyProvider(settings.netlify_api_token)
    if settings.deployment_provider == "vercel":
        return VercelProvider(settings.vercel_api_token)
    raise ValueError(f"Unknown DEPLOYMENT_PROVIDER '{settings.deployment_provider}'.")
