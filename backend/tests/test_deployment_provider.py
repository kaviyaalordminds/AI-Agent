import zipfile
from io import BytesIO

import pytest

from app.integrations.deployment.cloud_providers import NetlifyProvider, VercelProvider
from app.integrations.deployment.local_provider import LocalDeploymentProvider
from app.integrations.generation.errors import GenerationProviderNotConfiguredError, GenerationProviderRequestError
from app.integrations.storage.local_provider import LocalStorageProvider


class TestLocalDeploymentProvider:
    def test_capability_always_available_no_credentials_needed(self, tmp_path):
        storage = LocalStorageProvider(tmp_path / "storage")
        provider = LocalDeploymentProvider(storage)
        cap = provider.capability()
        assert cap.available is True
        assert cap.mode == "local"

    def test_deploy_produces_a_real_downloadable_zip(self, tmp_path):
        storage = LocalStorageProvider(tmp_path / "storage")
        provider = LocalDeploymentProvider(storage)
        result = provider.deploy(
            "my-site", {"index.html": b"<h1>Hi</h1>", "css/style.css": b"body{color:red}"}, "user-1"
        )
        assert result.provider == "local"
        assert result.live_url is None
        assert result.storage_ref is not None

        data = storage.read(result.storage_ref)
        archive = zipfile.ZipFile(BytesIO(data))
        names = set(archive.namelist())
        assert names == {"index.html", "css/style.css"}
        assert archive.read("index.html") == b"<h1>Hi</h1>"

    def test_deploy_rejects_empty_project(self, tmp_path):
        storage = LocalStorageProvider(tmp_path / "storage")
        provider = LocalDeploymentProvider(storage)
        with pytest.raises(GenerationProviderRequestError):
            provider.deploy("empty", {}, "user-1")


class TestCloudDeploymentProvidersHonestlyUnconfigured:
    def test_netlify_unconfigured_without_token(self):
        provider = NetlifyProvider(api_token=None)
        cap = provider.capability()
        assert cap.available is False
        assert "NETLIFY_API_TOKEN" in cap.reason
        with pytest.raises(GenerationProviderNotConfiguredError):
            provider.deploy("site", {"index.html": b"hi"}, "user-1")

    def test_vercel_unconfigured_without_token(self):
        provider = VercelProvider(api_token=None)
        cap = provider.capability()
        assert cap.available is False
        assert "VERCEL_API_TOKEN" in cap.reason
        with pytest.raises(GenerationProviderNotConfiguredError):
            provider.deploy("site", {"index.html": b"hi"}, "user-1")
