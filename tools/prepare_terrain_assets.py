#!/usr/bin/env python3
"""Prepare a bounded, content-addressed Civ V terrain asset package."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from civ5_terrain_assets import prepare


def main(argv=None):
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path, help="Civ V installation root (read only)")
    parser.add_argument("--output", type=Path, default=project / "Build" / "TerrainAssets",
                        help="Output directory (defaults to Build/TerrainAssets)")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.game, args.output)
    except (OSError, ValueError, KeyError, csv.Error) as error:
        parser.exit(2, f"terrain asset preparation failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
