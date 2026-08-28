#!/usr/bin/env python3
"""Copy the bundled modular GEO scRNA-seq pipeline into a working directory."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", help="Destination directory for the project")
    parser.add_argument("--force", action="store_true", help="Replace an existing destination")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    source = script_dir.parent / "assets" / "geo-scrna-modular-template"
    destination = Path(args.output_dir).expanduser().resolve()

    if not source.is_dir():
        raise SystemExit(f"Bundled project template not found: {source}")
    if destination.exists():
        if not args.force:
            raise SystemExit(f"Destination already exists: {destination}. Use --force to replace it.")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
