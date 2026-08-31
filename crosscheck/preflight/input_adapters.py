#!/usr/bin/env python3
"""input_adapters: alternate input modes for edna-crosscheck (PLAN §4 extension).

mode=species   input is a species list (.txt, one name/line; or .csv/.tsv with a
               `scientificName` column). Emits work/names.txt + params.json with
               `bbox: null` (the occurrence envelope is the OUTPUT, not a filter).
mode=coords    input is a points CSV (.csv/.tsv with decimalLatitude/decimalLongitude
               or lat/lon). Emits work/points.csv + params.json (bbox = points
               extent padded by --radius, default 0.5 deg). Taxa come later from
               checklist_builder (inverted query).

Both modes reuse the standard downstream chain (realm-router -> taxon-resolve ->
fishbase-traits -> ...) unchanged, per PLAN §4 architecture.

Usage:
  input_adapters.py species <input> <realm> <marker> <work_dir>
  input_adapters.py coords  <input> <realm> <marker> <work_dir> [radius_deg]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REQUIRED_REALMS = {"marine", "freshwater", "terrestrial"}
DEFAULT_ENV_LAYERS = {
    "bio_oracle": ["thetao", "so"],
    "worldclim_chelsa": ["bio1", "bio12", "elev"],
}
LAT_KEYS = ("decimalLatitude", "decimal latitude", "lat", "latitude")
LON_KEYS = ("decimalLongitude", "decimal longitude", "lon", "long", "longitude")


def _read_table(path: Path) -> list[dict]:
    """Read csv/tsv, sniffing the delimiter."""
    sample = path.read_text()[:4096]
    delim = "\t" if "\t" in sample.splitlines()[0] else ","
    with open(path) as f:
        return list(csv.DictReader(f, delimiter=delim))


def _col(row: dict, keys: tuple[str, ...]) -> str | None:
    low = {k.strip().lower(): v for k, v in row.items()}
    for k in keys:
        v = low.get(k.lower())
        if v is not None and v.strip():
            return v.strip()
    return None


def read_names(path: Path) -> list[str]:
    """Species list: plain text (one per line) or table with scientificName col."""
    if path.suffix.lower() in {".csv", ".tsv", ".tab"}:
        rows = _read_table(path)
        names = [_col(r, ("scientificName", "scientific name", "species", "taxon", "taxon_name")) for r in rows]
        out = [n for n in names if n]
    else:
        out = [n.strip() for n in path.read_text().splitlines() if n.strip()]
    if not out:
        raise SystemExit("input_adapters: FAIL no species names found in input")
    return sorted(set(out))


def read_points(path: Path) -> list[dict]:
    rows = _read_table(path)
    points = []
    for i, r in enumerate(rows):
        lat, lon = _col(r, LAT_KEYS), _col(r, LON_KEYS)
        if lat is None or lon is None:
            raise SystemExit(
                f"input_adapters: FAIL row {i + 1} missing coordinates (need decimalLatitude/decimalLongitude or lat/lon)")
        points.append({"point_id": r.get("point_id", f"P{i + 1}"),
                       "decimalLatitude": float(lat), "decimalLongitude": float(lon)})
    if not points:
        raise SystemExit("input_adapters: FAIL zero coordinate rows")
    return points


def write_params(work: Path, realm: str, marker: str, bbox: list[float] | None) -> None:
    params = {
        "skill_run": "edna-crosscheck",
        "input_mode": "species" if bbox is None else "coords",
        "realm": realm,
        "marker": marker,
        "bbox": bbox,
        "env_source": {"marine": "bio-oracle-v3", "freshwater": "worldclim-or-chelsa", "terrestrial": "worldclim-or-chelsa"},
        "env_layers": DEFAULT_ENV_LAYERS,
        "env_scenario": "present",
        "backbones": {"gbif": True, "worms": "marine-only", "fishbase": True},
    }
    (work / "params.json").write_text(json.dumps(params, indent=2))


def main() -> None:
    mode, inp, realm, marker, work_dir = sys.argv[1:6]
    if realm not in REQUIRED_REALMS:
        raise SystemExit(f"input_adapters: FAIL invalid realm {realm!r}")
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = Path(inp)

    if mode == "species":
        names = read_names(path)
        (work / "names.txt").write_text("\n".join(names) + "\n")
        write_params(work, realm, marker, bbox=None)  # inverted query: envelope IS the output
        print(f"input-adapters: species mode — {len(names)} unique names -> {work}/names.txt, bbox=None (inverted query)")

    elif mode == "coords":
        radius = float(sys.argv[6]) if len(sys.argv) >= 7 else 0.5
        points = read_points(path)
        pad = radius
        bbox = [min(p["decimalLongitude"] for p in points) - pad,
                min(p["decimalLatitude"] for p in points) - pad,
                max(p["decimalLongitude"] for p in points) + pad,
                max(p["decimalLatitude"] for p in points) + pad]
        (work / "points.csv").write_text(  # id-bearing: consumed by checklist_builder joins
            "point_id,decimalLatitude,decimalLongitude\n" +
            "".join(f"{p['point_id']},{p['decimalLatitude']},{p['decimalLongitude']}\n" for p in points))
        write_params(work, realm, marker, bbox)
        (work / "points_geo.csv").write_text(  # DwC-named: consumed by env-extract (scientificName = point_id placeholder,
            # mode B points have no species of their own; env values are per-POINT)
            "scientificName,decimalLatitude,decimalLongitude\n" +
            "".join(f"{p['point_id']},{p['decimalLatitude']},{p['decimalLongitude']}\n" for p in points))
        print(f"input-adapters: coords mode — {len(points)} points, radius={radius}deg, bbox={bbox}")

    else:
        raise SystemExit(f"input_adapters: FAIL unknown mode {mode!r} (species|coords)")


if __name__ == "__main__":
    main()