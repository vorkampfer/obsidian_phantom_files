#!/usr/bin/env python3
"""Scan an Obsidian vault, or open the desktop app if no arguments are given.

  python scan_vault.py
  python scan_vault.py /path/to/vault
  python scan_vault.py gui /path/to/vault
  python scan_vault.py trash-junk /path/to/vault
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phantom.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
