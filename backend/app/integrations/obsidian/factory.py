import uuid
from pathlib import Path

from app.core.config import get_settings
from app.integrations.obsidian.base import ObsidianProvider
from app.integrations.obsidian.local_vault_provider import LocalVaultProvider, provision_vault


def get_obsidian_provider(user_id: uuid.UUID) -> ObsidianProvider:
    """Returns a provider scoped to this user's own vault, provisioning it
    (folder structure + welcome note) on first use. Each user gets an
    isolated vault, matching how Projects/History are already per-user.
    """
    settings = get_settings()

    if settings.obsidian_provider != "local_vault":
        raise ValueError(f"Unknown OBSIDIAN_PROVIDER '{settings.obsidian_provider}'.")

    root = Path(settings.obsidian_vault_root) / str(user_id)
    if not root.exists():
        provision_vault(root)
    return LocalVaultProvider(root)


# General-purpose alias: KNOWLEDGE_PROVIDER=obsidian is the only backend
# today, so "the knowledge provider" and "the obsidian provider" are the
# same object per-user — see ObsidianProvider's docstring in base.py.
get_knowledge_provider = get_obsidian_provider
