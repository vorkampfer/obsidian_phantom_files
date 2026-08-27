"""Scan an Obsidian vault on disk. Obsidian does not need to be running."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import unquote

SKIP_DIRS = {".obsidian", ".trash", ".git", ".smart-env", "node_modules"}
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "ftp://", "obsidian://")
REPORT_BASENAMES = {
    "orphaned files output.md",
    "broken links output.md",
    "empty files.md",
    "empty folders.md",
    "files without tags.md",
    "find orphaned files plugin output.md",
}

WIKILINK_RE = re.compile(
    r"!?"
    r"\[\["
    r"([^\]|#]*)"
    r"(?:#[^\]|]*)?"
    r"(?:\|[^\]]*)?"
    r"\]\]"
)
MD_LINK_RE = re.compile(
    r"!?"
    r"\[[^\]]*\]"
    r"\("
    r"<?([^)\s>]+(?:\s+[^)\s>]+)*)>?"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?"
    r"\)"
)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
HEADING_OR_BLOCK_RE = re.compile(r"[#^].*")
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.S)
BODY_TAG_RE = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_/\-]*)")


@dataclass
class Link:
    target: str
    source: str
    kind: str  # wiki | markdown | canvas


@dataclass
class Settings:
    ignore_dirs: list[str] = field(default_factory=list)
    ignore_files: list[str] = field(default_factory=list)
    ignore_extensions: list[str] = field(default_factory=list)
    ignore_tags: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    vault: str
    files: list[str]
    broken: list[Link] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    junk: list[str] = field(default_factory=list)
    empty_files: list[str] = field(default_factory=list)
    empty_folders: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "files": len(self.files),
            "broken": len(self.broken),
            "orphans": len(self.orphans),
            "junk": len(self.junk),
            "empty_files": len(self.empty_files),
            "empty_folders": len(self.empty_folders),
        }


class VaultIndex:
    """Maps Obsidian-style link targets to vault-relative posix paths."""

    def __init__(self, root: str, files: list[str]) -> None:
        self.root = root
        self.files = files
        self.by_path: dict[str, str] = {}
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for rel in files:
            self.by_path[rel.lower()] = rel
            name = os.path.basename(rel).lower()
            self.by_name[name].append(rel)
            stem, ext = os.path.splitext(name)
            if ext == ".md" and stem:
                self.by_name[stem].append(rel)

    def resolve(self, target: str, source: str) -> str | None:
        target = normalize_target(target)
        if not target:
            return source

        candidates = [target]
        if not os.path.splitext(target)[1]:
            candidates.append(target + ".md")

        source_dir = os.path.dirname(source)
        for cand in candidates:
            rel_from_source = posix_norm(os.path.join(source_dir, cand))
            hit = self.by_path.get(rel_from_source.lower())
            if hit:
                return hit
            hit = self.by_path.get(cand.lower())
            if hit:
                return hit

        name = os.path.basename(candidates[-1]).lower()
        matches = self.by_name.get(name, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return min(matches, key=len)
        stem = os.path.splitext(name)[0]
        if stem != name:
            matches = self.by_name.get(stem, [])
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return min(matches, key=len)
        return None


def posix_norm(path: str) -> str:
    path = path.replace("\\", "/")
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def normalize_target(raw: str) -> str:
    target = unquote(raw.strip())
    target = HEADING_OR_BLOCK_RE.sub("", target)
    target = target.split("|", 1)[0].strip()
    return posix_norm(target)


def is_external(target: str) -> bool:
    lowered = target.strip().lower()
    return lowered.startswith(EXTERNAL_SCHEMES) or lowered.startswith("#")


def strip_code(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(kept)


def extract_tags(text: str) -> set[str]:
    tags: set[str] = set()
    match = FRONTMATTER_RE.match(text)
    if match:
        fm = match.group(1)
        inline = re.search(r"^tags:\s*\[(.*?)\]", fm, re.M)
        if inline:
            for part in inline.group(1).split(","):
                tag = part.strip().strip("'\"").lstrip("#")
                if tag:
                    tags.add(tag)
        else:
            in_list = False
            for raw in fm.splitlines():
                if re.match(r"^tags:\s*$", raw):
                    in_list = True
                    continue
                if in_list:
                    item = re.match(r"^\s+-\s+(.+)", raw)
                    if item:
                        tag = item.group(1).strip().strip("'\"").lstrip("#")
                        if tag:
                            tags.add(tag)
                        continue
                    if re.match(r"^\S", raw):
                        in_list = False
                line = re.match(r"^tags:\s+(\S.*)$", raw)
                if line:
                    for part in line.group(1).split(","):
                        tag = part.strip().strip("'\"").lstrip("#")
                        if tag:
                            tags.add(tag)
    for tag in BODY_TAG_RE.findall(strip_code(text)):
        tags.add(tag)
    return tags


def extract_markdown_links(text: str, source: str) -> list[Link]:
    text = strip_code(text)
    links: list[Link] = []
    for match in WIKILINK_RE.finditer(text):
        links.append(Link(target=match.group(1).strip(), source=source, kind="wiki"))
    for match in MD_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if is_external(target):
            continue
        links.append(Link(target=target, source=source, kind="markdown"))
    return links


def extract_canvas_links(text: str, source: str) -> list[Link]:
    try:
        data = json.loads(text or "{}")
    except json.JSONDecodeError:
        return []
    links: list[Link] = []
    for node in data.get("nodes") or []:
        node_type = node.get("type")
        if node_type == "file" and node.get("file"):
            links.append(Link(target=node["file"], source=source, kind="canvas"))
        elif node_type == "text" and node.get("text"):
            for link in extract_markdown_links(node["text"], source):
                links.append(Link(target=link.target, source=source, kind="canvas"))
    return links


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or (name.startswith(".") and name not in {".", ".."})


def is_junk_filename(name: str) -> bool:
    return name in JUNK_NAMES or name.startswith("._")


def looks_like_vault(root: str) -> bool:
    return os.path.isdir(os.path.join(root, ".obsidian"))


def normalize_ignore(value: str) -> str:
    return value.strip().strip("/").replace("\\", "/").lower()


def path_ignored(rel: str, settings: Settings) -> bool:
    rel_n = rel.replace("\\", "/").lower()
    base = os.path.basename(rel_n)
    if base in REPORT_BASENAMES:
        return True
    for directory in settings.ignore_dirs:
        prefix = normalize_ignore(directory)
        if prefix and (rel_n == prefix or rel_n.startswith(prefix + "/")):
            return True
    for name in settings.ignore_files:
        wanted = normalize_ignore(name)
        if rel_n == wanted or base == wanted:
            return True
    ext = os.path.splitext(rel_n)[1].lstrip(".")
    ignored_exts = {e.lstrip(".").lower() for e in settings.ignore_extensions}
    return bool(ext) and ext in ignored_exts


def walk_vault(root: str) -> tuple[list[str], list[str], list[str]]:
    files: list[str] = []
    junk: list[str] = []
    empty_folders: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not should_skip_dir(name)]
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        visible = [name for name in filenames if not is_junk_filename(name)]
        if rel_dir and not visible and not dirnames:
            empty_folders.append(rel_dir.replace(os.sep, "/"))
        for name in filenames:
            rel = name if not rel_dir else f"{rel_dir.replace(os.sep, '/')}/{name}"
            if is_junk_filename(name):
                junk.append(rel)
            elif not name.startswith("."):
                files.append(rel)
    files.sort()
    junk.sort()
    empty_folders.sort()
    return files, junk, empty_folders


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def is_empty_note(path: str, rel: str) -> bool:
    if not rel.lower().endswith(".md"):
        try:
            return os.path.getsize(path) == 0
        except OSError:
            return False
    text = read_text(path).strip()
    if not text:
        return True
    if text.startswith("---"):
        rest = text[3:]
        end = rest.find("\n---")
        if end != -1:
            return not rest[end + 4 :].strip()
    return False


def collect_links(
    root: str,
    files: list[str],
    settings: Settings,
    tags_by_file: dict[str, set[str]],
) -> list[Link]:
    ignore_tags = {tag.lstrip("#").lower() for tag in settings.ignore_tags}
    links: list[Link] = []
    for rel in files:
        if path_ignored(rel, settings):
            continue
        if ignore_tags and tags_by_file.get(rel, set()) & ignore_tags:
            continue
        path = os.path.join(root, rel)
        lower = rel.lower()
        if lower.endswith(".md"):
            links.extend(extract_markdown_links(read_text(path), rel))
        elif lower.endswith(".canvas"):
            links.extend(extract_canvas_links(read_text(path), rel))
    return links


def scan(root: str, settings: Settings | None = None) -> ScanResult:
    settings = settings or Settings()
    root = os.path.abspath(root)
    files, junk, empty_folders = walk_vault(root)
    tags_by_file: dict[str, set[str]] = {}
    for rel in files:
        if rel.lower().endswith(".md"):
            tags_by_file[rel] = {tag.lower() for tag in extract_tags(read_text(os.path.join(root, rel)))}

    index = VaultIndex(root, files)
    links = collect_links(root, files, settings, tags_by_file)
    ignore_tags = {tag.lstrip("#").lower() for tag in settings.ignore_tags}

    incoming: set[str] = set()
    broken: list[Link] = []
    for link in links:
        resolved = index.resolve(link.target, link.source)
        if resolved:
            incoming.add(resolved)
        else:
            broken.append(link)

    orphans = []
    empty_files = []
    for rel in files:
        if path_ignored(rel, settings):
            continue
        if ignore_tags and tags_by_file.get(rel, set()) & ignore_tags:
            continue
        if rel not in incoming:
            orphans.append(rel)
        if is_empty_note(os.path.join(root, rel), rel):
            empty_files.append(rel)

    empty_folders = [folder for folder in empty_folders if not path_ignored(folder, settings)]
    return ScanResult(
        vault=root,
        files=files,
        broken=broken,
        orphans=orphans,
        junk=junk,
        empty_files=empty_files,
        empty_folders=empty_folders,
    )
