"""Best-effort cross-check of OBSIDIAN_VAULT_ID against the Obsidian
desktop app's own config file.

Obsidian assigns every vault a random id the first time it's opened,
recorded in a small JSON file the app itself maintains (obsidian.json),
keyed by that id with each entry's real filesystem path. This module reads
that file — read-only, never written to — to confirm OBSIDIAN_VAULT_PATH
actually is the vault the user thinks it is. This is genuinely useful (not
decorative): pointing the backend at the wrong folder with a similar name
would otherwise fail silently.

The check is inherently best-effort: obsidian.json only exists on the
machine Obsidian itself runs on, at an OS-specific location. When it can't
be found or parsed, that is reported honestly as "unverifiable" — never
upgraded to "verified" just because nothing contradicted it.
"""
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("integrations.obsidian")


@dataclass
class VaultIdCheck:
    status: str  # "verified" | "mismatch" | "unverifiable"
    detail: str


def _candidate_config_paths() -> list[Path]:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "obsidian" / "obsidian.json")
    home = Path.home()
    candidates.append(home / "Library" / "Application Support" / "obsidian" / "obsidian.json")
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        candidates.append(Path(xdg_config) / "obsidian" / "obsidian.json")
    candidates.append(home / ".config" / "obsidian" / "obsidian.json")
    return candidates


def locate_obsidian_app_config() -> Path | None:
    for path in _candidate_config_paths():
        if path.is_file():
            return path
    return None


def verify_vault_id(vault_id: str, vault_path: Path) -> VaultIdCheck:
    """Looks up `vault_id` in the Obsidian app's own obsidian.json (if
    reachable on this machine) and compares its recorded path against
    `vault_path`. Never raises — any failure to locate/parse the file is
    reported as "unverifiable", not treated as an error."""
    config_path = locate_obsidian_app_config()
    if config_path is None:
        return VaultIdCheck(
            status="unverifiable",
            detail="Obsidian's own app config was not found on this machine — vault id was not cross-checked.",
        )

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Obsidian app config at %s: %s", config_path, exc)
        return VaultIdCheck(
            status="unverifiable",
            detail=f"Obsidian's app config at {config_path} could not be read — vault id was not cross-checked.",
        )

    vaults = raw.get("vaults", {}) if isinstance(raw, dict) else {}
    entry = vaults.get(vault_id)
    if entry is None:
        return VaultIdCheck(
            status="unverifiable",
            detail=f"Vault id '{vault_id}' was not found in Obsidian's app config — it may not have been opened in Obsidian on this machine yet.",
        )

    registered_path = entry.get("path") if isinstance(entry, dict) else None
    if not registered_path:
        return VaultIdCheck(status="unverifiable", detail="Obsidian's app config has no path recorded for this vault id.")

    try:
        matches = Path(registered_path).resolve() == vault_path.resolve()
    except OSError:
        matches = str(Path(registered_path)) == str(vault_path)

    if matches:
        return VaultIdCheck(status="verified", detail=f"Vault id '{vault_id}' matches the configured vault path.")
    return VaultIdCheck(
        status="mismatch",
        detail=(
            f"Vault id '{vault_id}' is registered in Obsidian against '{registered_path}', "
            f"which does not match the configured OBSIDIAN_VAULT_PATH ('{vault_path}')."
        ),
    )
