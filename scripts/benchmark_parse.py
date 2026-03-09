#!/usr/bin/env python3
"""Benchmark parser performance with and without geometry extraction.

Usage:
    python scripts/benchmark_parse.py data/AdvancedProject.ifc
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ifc_mcp.core.parser import parse_ifc


def benchmark(filepath: str) -> None:
    path = Path(filepath)
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"File: {path.name} ({size_mb:.1f} MB)")
    print()

    # Warm-up: open file once to prime OS cache
    parse_ifc(str(path), extract_geometry=False)

    # Benchmark without geometry (single run)
    start = time.monotonic()
    parsed_no_geom = parse_ifc(str(path), extract_geometry=False)
    elapsed_no_geom = time.monotonic() - start
    entity_count = len(parsed_no_geom.entities)

    # Benchmark with geometry (single run)
    start = time.monotonic()
    parsed_with_geom = parse_ifc(str(path), extract_geometry=True)
    elapsed_with_geom = time.monotonic() - start
    bounds_count = sum(1 for e in parsed_with_geom.entities.values() if e.geometry_bounds is not None)

    speedup = elapsed_with_geom / elapsed_no_geom if elapsed_no_geom > 0 else float("inf")

    print(f"Entities: {entity_count}")
    print(f"Entities with geometry bounds: {bounds_count}")
    print()
    print(f"Without geometry: {elapsed_no_geom:.2f}s")
    print()
    print(f"With geometry (batch iterator): {elapsed_with_geom:.2f}s")
    print()
    print(f"Speedup (no-geometry vs with-geometry): {speedup:.1f}x")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark IFC parser geometry extraction")
    parser.add_argument("filepath", help="Path to IFC file")
    args = parser.parse_args()
    benchmark(args.filepath)
