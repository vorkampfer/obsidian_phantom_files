"""Command-line and GUI entry points."""

from __future__ import annotations

import argparse
import os
import sys

from phantom.config import load_settings
from phantom.core import looks_like_vault, scan
from phantom.report import format_broken, write_report
from phantom.actions import trash_paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="phantom",
        description=(
            "Scan an Obsidian vault folder for broken links, orphaned files, "
            "macOS AppleDouble junk, and empty notes. Obsidian does not need "
            "to be open. Run with no arguments to open the GUI."
        )
    )
    sub = parser.add_subparsers(dest="command")

    scan_p = sub.add_parser("scan", help="Print a scan report in the terminal")
    _add_scan_flags(scan_p)

    gui_p = sub.add_parser("gui", help="Open the desktop app")
    gui_p.add_argument("vault", nargs="?", help="Optional vault path to prefill")

    trash_p = sub.add_parser("trash-junk", help="Move ._ and desktop junk files into vault/.trash")
    trash_p.add_argument("vault", help="Path to the vault root")
    trash_p.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files. Without this flag, only print what would move.",
    )
    trash_p.add_argument("--config", help="Path to a phantom.toml settings file")

    return parser.parse_args(argv)


def _add_scan_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("vault", help="Path to the vault root (the folder that contains .obsidian)")
    parser.add_argument("--broken", action="store_true", help="Show broken / phantom links only")
    parser.add_argument("--orphans", action="store_true", help="Show files with no incoming links")
    parser.add_argument("--junk", action="store_true", help="Show ._ AppleDouble and desktop junk files")
    parser.add_argument("--empty", action="store_true", help="Show empty files and empty folders")
    parser.add_argument("--write-report", metavar="FILE", help="Write a markdown report to FILE")
    parser.add_argument("--config", help="Path to a phantom.toml settings file")
    parser.add_argument("--gui", action="store_true", help="Open the desktop app instead of printing")


def print_section(title: str, rows: list[str]) -> None:
    print(f"\n{title} ({len(rows)})")
    print("-" * 60)
    if not rows:
        print("  (none)")
        return
    for row in rows:
        print(f"  {row}")


def run_scan(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.vault)
    if not os.path.isdir(root):
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    if not looks_like_vault(root):
        print(
            f"Warning: {root} has no .obsidian folder. Scanning it as a vault anyway.",
            file=sys.stderr,
        )
    settings, _ = load_settings(getattr(args, "config", None), root)
    result = scan(root, settings)
    show_all = not any((args.broken, args.orphans, args.junk, args.empty))
    print(f"Vault: {result.vault}")
    print(f"Files scanned: {len(result.files)}")
    if show_all or args.broken:
        print_section("Broken / phantom links", format_broken(result.broken))
    if show_all or args.orphans:
        print_section("Orphaned files (no incoming links)", result.orphans)
    if show_all or args.junk:
        print_section("Junk files (AppleDouble / desktop metadata)", result.junk)
    if show_all or args.empty:
        print_section("Empty files", result.empty_files)
        print_section("Empty folders", result.empty_folders)
    if args.write_report:
        sections = []
        if args.broken:
            sections.append("broken")
        if args.orphans:
            sections.append("orphans")
        if args.junk:
            sections.append("junk")
        if args.empty:
            sections.append("empty")
        write_report(args.write_report, result, sections or None)
        print(f"\nWrote report: {args.write_report}")
    return 0


def run_trash(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.vault)
    if not os.path.isdir(root):
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2
    settings, _ = load_settings(args.config, root)
    result = scan(root, settings)
    if not result.junk:
        print("No junk files found.")
        return 0
    planned = trash_paths(root, result.junk, apply=args.apply)
    verb = "Moved" if args.apply else "Would move"
    print(f"{verb} {len(planned)} file(s) into {os.path.join(root, '.trash')}:")
    for src, dest in planned:
        print(f"  {src} -> {dest}")
    if not args.apply:
        print("\nRe-run with --apply to move them.")
    return 0


def launch_gui(vault: str | None = None) -> int:
    from phantom.gui import run_gui

    return run_gui(vault)


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        return launch_gui()
    if raw[0] == "--gui":
        return launch_gui(raw[1] if len(raw) > 1 else None)
    if raw[0] not in {"scan", "gui", "trash-junk", "-h", "--help"} and not raw[0].startswith("-"):
        raw = ["scan", *raw]
    args = parse_args(raw)
    if args.command == "gui":
        return launch_gui(args.vault)
    if args.command == "trash-junk":
        return run_trash(args)
    if args.command == "scan":
        if args.gui:
            return launch_gui(args.vault)
        return run_scan(args)
    return launch_gui()
