"""Move vault files into the vault's .trash folder. Never deletes in place."""

from __future__ import annotations

import os
import shutil


def trash_destination(vault: str, rel: str) -> str:
    return os.path.join(vault, ".trash", rel.replace("/", os.sep))


def unique_destination(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = f"{base}.{n}{ext}"
        if not os.path.exists(candidate):
            return candidate
        n += 1


def trash_paths(vault: str, rels: list[str], apply: bool = False) -> list[tuple[str, str]]:
    """Return (source, destination) pairs. Moves only when apply is True."""
    planned: list[tuple[str, str]] = []
    for rel in rels:
        src = os.path.join(vault, rel)
        dest = unique_destination(trash_destination(vault, rel))
        planned.append((src, dest))
        if not apply:
            continue
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
    return planned
