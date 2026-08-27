# Obsidian Phantom

Scan an [Obsidian](https://obsidian.md) vault **from disk**, without opening Obsidian and without installing a community plugin.

A vault is just a folder of markdown notes and attachments. This tool walks that folder, parses `[[wikilinks]]` and markdown links, and reports:

- **Junk files** — macOS/Windows metadata clutter
- **Broken / phantom links** — `[[links]]` whose target file does not exist
- **Orphans** — files that exist but nothing points at them
- **Empty files and empty folders**

It is inspired by community plugins such as [find-unlinked-files](https://github.com/Vinzent03/find-unlinked-files), but it runs as a normal Python CLI and an optional PySide6 desktop app.

## Safety: nothing is permanently deleted

This tool does **not** `rm` files.

`trash-junk` **moves** matching junk files into the vault’s `.trash` folder (the same place Obsidian uses for trash). You can restore them from there.

| Command | What it does |
|---|---|
| `phantom trash-junk ~/Documents` | Dry-run. Prints what *would* move. Touches nothing. |
| `phantom trash-junk ~/Documents --apply` | Moves **junk files only** into `~/Documents/.trash` |

Without `--apply`, it is always a preview.

The GUI button **Move junk to .trash** asks for confirmation, then does the same move.

### What is never touched

- Real notes (`.md` files that are not junk metadata)
- Broken-link *sources* (the note that *contains* a bad `[[link]]`)
- Orphans
- Empty files / folders (listed only; there is no delete command for them)

If a note shows up under **Broken links**, that note is the *source*. It is not being nominated for trash.

Example:

```
[["$EUID" -eq 0]]  <-  Bash_Scripts_Snippets.md (wiki)
```

Means: inside `Bash_Scripts_Snippets.md` there is bash test syntax `[[ "$EUID" -eq 0 ]]`, which looks like a wikilink. The scanner cannot find a note with that name, so it reports a broken link. The snippet file itself is valid and is **not** junk.

## What counts as junk

Junk is **filename metadata only**. A file is junk if its name is:

- `._*` — macOS AppleDouble sidecar files (the usual clutter from Finder/iCloud/zip on a Mac)
- `.DS_Store`
- `Thumbs.db`
- `desktop.ini`

A normal note such as `Bash_Scripts_Snippets.md` is **never** junk. An AppleDouble sidecar next to it would be named `._Bash_Scripts_Snippets.md` — that sidecar is junk; the note is not.

## Requirements

- Python 3.11+
- [PySide6](https://pypi.org/project/PySide6/) for the desktop app (`pip install PySide6`)

The scanner itself is stdlib. PySide6 is only needed for the GUI.

## Run it

From this project directory:

```bash
# Desktop app (no arguments)
python scan_vault.py
python -m phantom
python -m phantom gui ~/Documents

# Terminal scan
python scan_vault.py ~/Documents
python -m phantom scan ~/Documents
python -m phantom scan ~/Documents --junk
python -m phantom scan ~/Documents --broken
python -m phantom scan ~/Documents --orphans
python -m phantom scan ~/Documents --empty
python -m phantom scan ~/Documents --write-report /tmp/vault-scan.md
```

Point it at the **vault root** (the folder that contains `.obsidian`), not a parent of several vaults unless you really mean to scan that whole tree.

### Clean junk (move to `.trash`)

```bash
# Preview first — always do this
python -m phantom trash-junk ~/Documents

# If the listed paths are only ._ / .DS_Store style files:
python -m phantom trash-junk ~/Documents --apply
```

After `--apply`, junk lives under `~/Documents/.trash/...` with the original relative path preserved. Obsidian can restore from `.trash`. Collisions get a numeric suffix (`.1`, `.2`, …).

## GUI

The window lists broken links, orphans, junk, and empty files/folders.

- **Ignore rules** (`Ctrl+,`) — skip folders, files, extensions, or tags
- **Export report** — markdown report
- **Move junk to .trash** — confirmation, then move junk only
- Double-click or **Open selected** — open that file

## Optional config

Copy `phantom.toml.example` to `phantom.toml` in the vault root (or pass `--config`):

```toml
ignore_dirs = ["Templates", "Archive"]
ignore_files = ["Home.md"]
ignore_extensions = ["css", "js"]
ignore_tags = ["keep"]
```

Ignored notes are skipped for orphan/broken/empty reporting. Junk (AppleDouble and desktop metadata) is still found vault-wide so you can clean it.

## How scanning works

Obsidian does not need to be running. The AppImage/desktop app is irrelevant; the vault is files on disk.

1. Walk the folder with `os.walk` (skips `.obsidian`, `.trash`, `.git`, and other hidden directories).
2. Parse `[[wikilinks]]`, `![[embeds]]`, markdown links, and canvas file nodes.
3. Skip example links inside fenced code blocks and inline backticks.
4. Resolve targets the way Obsidian roughly does: path relative to the source, vault-relative path, then unique filename (with `.md` implied).
5. Compare resolved targets to files that actually exist.

**Broken** = the link target does not exist.  
**Orphan** = the file exists but has no incoming links.  
**Junk** = metadata filename, listed above.

## Tests

```bash
PYTHONPATH=. python -m unittest tests.test_core -v
```

## License

Use and modify freely for your own vaults.
