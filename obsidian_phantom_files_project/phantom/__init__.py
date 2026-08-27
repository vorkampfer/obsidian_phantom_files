"""Obsidian Phantom: find broken links, orphans, and junk files in a vault."""

from phantom.core import Link, ScanResult, Settings, scan

__version__ = "0.1.0"
__all__ = ["Link", "ScanResult", "Settings", "scan", "__version__"]
