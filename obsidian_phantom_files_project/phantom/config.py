from __future__ import annotations

import os
import tomllib

from phantom.core import Settings


def load_settings(path: str | None = None, vault: str | None = None) -> tuple[Settings, str | None]:
    """Load settings from an explicit toml file, vault/phantom.toml, or ./phantom.toml."""
    candidates = []
    if path:
        candidates.append(path)
    if vault:
        candidates.append(os.path.join(vault, "phantom.toml"))
    candidates.append(os.path.join(os.getcwd(), "phantom.toml"))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return _from_toml(candidate), candidate
    return Settings(), None


def _from_toml(path: str) -> Settings:
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    return Settings(
        ignore_dirs=_as_list(data.get("ignore_dirs")),
        ignore_files=_as_list(data.get("ignore_files")),
        ignore_extensions=_as_list(data.get("ignore_extensions")),
        ignore_tags=_as_list(data.get("ignore_tags")),
    )


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
