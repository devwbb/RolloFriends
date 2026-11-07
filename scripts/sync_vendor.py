#!/usr/bin/env python3
"""Copy the standalone library into the integration for local/HACS installs.

The canonical source is ``src/aiosmartfriends``. Home Assistant cannot pip
install an unreleased package on the test VM, so the integration bundles a
byte-identical copy. Run this script after every library change.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "aiosmartfriends"
TARGET = ROOT / "custom_components" / "smartfriends_box" / "vendor" / "aiosmartfriends"


def main() -> int:
    if not SOURCE.is_dir():
        print(f"Source package not found: {SOURCE}", file=sys.stderr)
        return 1
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SOURCE,
        TARGET,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    print(f"Copied {SOURCE} -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
