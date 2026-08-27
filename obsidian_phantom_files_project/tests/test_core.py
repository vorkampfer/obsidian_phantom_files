from __future__ import annotations

import json
import os
import tempfile
import unittest

from phantom.actions import trash_paths
from phantom.core import Settings, extract_tags, scan


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="obsidian-phantom-")
        os.makedirs(os.path.join(self.root, ".obsidian"))
        os.makedirs(os.path.join(self.root, "notes"))
        os.makedirs(os.path.join(self.root, "empty_dir"))
        os.makedirs(os.path.join(self.root, "Templates"))
        _write(
            os.path.join(self.root, "Home.md"),
            "See [[Real Note]] and [[Missing Note]] and [[notes/Nested]].\n"
            "Also [md](notes/Nested.md) and ![[photo.png]].\n"
            "External [x](https://example.com) should be ignored.\n"
            "Code example: `[[not-a-link]]`\n"
            "```\n[[also-not-a-link]]\n```\n",
        )
        _write(os.path.join(self.root, "notes", "Nested.md"), "back to [[Home]]\n")
        _write(os.path.join(self.root, "Real Note.md"), "# real\n")
        _write(os.path.join(self.root, "Orphan.md"), "nobody links here\n")
        _write(os.path.join(self.root, "empty.md"), "")
        _write(os.path.join(self.root, "Templates", "Daily.md"), "template\n")
        _write(
            os.path.join(self.root, "Kept.md"),
            "---\ntags:\n  - keep\n---\norphan but tagged\n",
        )
        with open(os.path.join(self.root, "photo.png"), "wb") as handle:
            handle.write(b"\x89PNG")
        _write(os.path.join(self.root, "._Home.md"), "appledouble")
        _write(os.path.join(self.root, ".DS_Store"), "junk")
        _write(
            os.path.join(self.root, "board.canvas"),
            json.dumps(
                {
                    "nodes": [
                        {"type": "file", "file": "Home.md"},
                        {"type": "text", "text": "See [[Ghost Canvas]]"},
                    ]
                }
            ),
        )

    def test_broken_orphans_junk_and_empty(self) -> None:
        result = scan(self.root)
        broken = {link.target for link in result.broken}
        self.assertIn("Missing Note", broken)
        self.assertIn("Ghost Canvas", broken)
        self.assertNotIn("not-a-link", broken)
        self.assertNotIn("also-not-a-link", broken)
        self.assertIn("Orphan.md", result.orphans)
        self.assertNotIn("Home.md", result.orphans)
        self.assertNotIn("photo.png", result.orphans)
        self.assertIn("._Home.md", result.junk)
        self.assertIn(".DS_Store", result.junk)
        self.assertIn("empty.md", result.empty_files)
        self.assertIn("empty_dir", result.empty_folders)

    def test_ignore_dir_and_tag(self) -> None:
        result = scan(
            self.root,
            Settings(ignore_dirs=["Templates"], ignore_tags=["keep"]),
        )
        self.assertNotIn("Templates/Daily.md", result.orphans)
        self.assertNotIn("Kept.md", result.orphans)

    def test_extract_tags(self) -> None:
        tags = extract_tags("---\ntags:\n  - keep\n  - inbox\n---\n#body-tag\n")
        self.assertEqual(tags, {"keep", "inbox", "body-tag"})

    def test_trash_junk_dry_run_does_not_move(self) -> None:
        result = scan(self.root)
        planned = trash_paths(self.root, result.junk, apply=False)
        self.assertTrue(planned)
        self.assertTrue(os.path.exists(os.path.join(self.root, "._Home.md")))
        self.assertFalse(os.path.isdir(os.path.join(self.root, ".trash")))


if __name__ == "__main__":
    unittest.main()
