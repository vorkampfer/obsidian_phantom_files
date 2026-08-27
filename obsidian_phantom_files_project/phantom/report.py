from __future__ import annotations

from collections import defaultdict

from phantom.core import Link, ScanResult


def format_broken(links: list[Link]) -> list[str]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for link in links:
        grouped[link.target].append(f"{link.source} ({link.kind})")
    rows = []
    for target in sorted(grouped):
        sources = ", ".join(sorted(set(grouped[target])))
        rows.append(f"[[{target}]]  <-  {sources}")
    return rows


def grouped_broken(links: list[Link]) -> list[tuple[str, str, str]]:
    """Return (target, sources, kinds) rows for tables."""
    grouped: dict[str, list[Link]] = defaultdict(list)
    for link in links:
        grouped[link.target].append(link)
    rows = []
    for target in sorted(grouped):
        found = grouped[target]
        sources = ", ".join(sorted({link.source for link in found}))
        kinds = ", ".join(sorted({link.kind for link in found}))
        rows.append((target, sources, kinds))
    return rows


def markdown_report(result: ScanResult, sections: list[str] | None = None) -> str:
    wanted = set(sections or ["broken", "orphans", "junk", "empty"])
    lines = [
        f"# Vault scan: `{result.vault}`",
        "",
        f"- Files scanned: {len(result.files)}",
        f"- Broken links: {len(result.broken)}",
        f"- Orphaned files: {len(result.orphans)}",
        f"- Junk files: {len(result.junk)}",
        f"- Empty files: {len(result.empty_files)}",
        f"- Empty folders: {len(result.empty_folders)}",
        "",
    ]
    mapping = []
    if "broken" in wanted:
        mapping.append(("Broken / phantom links", format_broken(result.broken)))
    if "orphans" in wanted:
        mapping.append(("Orphaned files (no incoming links)", result.orphans))
    if "junk" in wanted:
        mapping.append(("Junk files (AppleDouble / desktop metadata)", result.junk))
    if "empty" in wanted:
        mapping.append(("Empty files", result.empty_files))
        mapping.append(("Empty folders", result.empty_folders))
    for title, rows in mapping:
        lines.append(f"## {title}")
        lines.append("")
        if rows:
            lines.extend(f"- `{row}`" for row in rows)
        else:
            lines.append("- *(none)*")
        lines.append("")
    return "\n".join(lines)


def write_report(path: str, result: ScanResult, sections: list[str] | None = None) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(markdown_report(result, sections))
