import io
import uuid
import zipfile

from app.integrations.capability import CapabilityStatus
from app.integrations.deployment.base import DeploymentProvider, DeploymentResult
from app.integrations.generation.errors import GenerationProviderRequestError
from app.integrations.storage.base import StorageProvider


class LocalDeploymentProvider(DeploymentProvider):
    """Real, working "deployment" for local development: zips the given
    project files and stores the archive via StorageProvider so it can be
    downloaded — no hosting credentials required. This is genuinely
    useful (a real downloadable artifact), not a placeholder; it's simply
    not a *live* deployment the way NetlifyProvider/VercelProvider would be."""

    def __init__(self, storage_provider: StorageProvider) -> None:
        self._storage = storage_provider

    def capability(self) -> CapabilityStatus:
        return CapabilityStatus(
            available=True,
            provider="local",
            mode="local",
            reason="Local deployment packages a downloadable zip archive — no credentials required.",
        )

    def deploy(self, project_name: str, files: dict[str, bytes], owner_id: str) -> DeploymentResult:
        if not files:
            raise GenerationProviderRequestError("Cannot deploy an empty project (no files given).")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative_path, content in files.items():
                archive.writestr(relative_path, content)

        stored = self._storage.write(
            "deployments", owner_id, f"{uuid.uuid4()}.zip", buffer.getvalue()
        )
        return DeploymentResult(provider="local", storage_ref=stored.ref, live_url=None)
