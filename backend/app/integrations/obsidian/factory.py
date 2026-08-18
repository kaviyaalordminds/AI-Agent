import logging
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.integrations.obsidian.base import ObsidianProvider
from app.integrations.obsidian.local_vault_provider import LocalVaultProvider, provision_vault

logger = logging.getLogger("integrations.obsidian")


def get_obsidian_provider(user_id: uuid.UUID) -> ObsidianProvider:
    """Returns a provider scoped to a vault, provisioning folder structure
    + a welcome note on first use — but ONLY when that vault directory
    doesn't already exist, so a real pre-existing Obsidian vault (see
    obsidian_vault_path below) is never overwritten.

    Two modes, selected by configuration:
    - Default (OBSIDIAN_VAULT_PATH unset): each user gets an isolated
      vault at {obsidian_vault_root}/{user_id}/, matching how
      Projects/History are already per-user.
    - OBSIDIAN_VAULT_PATH set: every user on this backend operates
      directly on that single, exact directory — intended for a
      single-user personal deployment pointed at a real, already-
      existing Obsidian vault (see app/core/config.py for the tradeoff).
    """
    settings = get_settings()

    if settings.obsidian_provider != "local_vault":
        raise ValueError(f"Unknown OBSIDIAN_PROVIDER '{settings.obsidian_provider}'.")

    if settings.obsidian_vault_path:
        root = Path(settings.obsidian_vault_path)
        if not root.exists():
            logger.warning(
                "OBSIDIAN_VAULT_PATH is configured but does not exist yet: %s — provisioning a new vault there.",
                root,
            )
            provision_vault(root)
        return LocalVaultProvider(root, vault_id=settings.obsidian_vault_id)

    root = Path(settings.obsidian_vault_root) / str(user_id)
    if not root.exists():
        provision_vault(root)
    return LocalVaultProvider(root)


# General-purpose alias: KNOWLEDGE_PROVIDER=obsidian is the only backend
# today, so "the knowledge provider" and "the obsidian provider" are the
# same object per-user — see ObsidianProvider's docstring in base.py.
get_knowledge_provider = get_obsidian_provider
