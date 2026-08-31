#!/usr/bin/env python3
"""preflight: validate the input ASV/occurrence table + write the run
manifest (params.json contract, PLAN §11.1).

Required input columns (nf-edna ASV table / DwC-shaped occurrence table):
  scientificName, decimalLatitude, decimalLongitude, eventDate

Usage: python3 preflight.py <input.csv> <realm> <marker> <out_params.json> \
           [minLon minLat maxLon maxLat]
"""
from __future__ import annotations
import csv
import json
import sys

REQUIRED_COLS = {"scientificName", "decimalLatitude", "decimalLongitude", "eventDate"}
VALID_REALMS = {"marine", "freshwater", "terrestrial"}

DEFAULT_ENV_LAYERS = {
    "bio_oracle": ["thetao", "so"],
    "worldclim_chelsa": ["bio1", "bio12", "elev"],
}


def main() -> None:
    input_csv, realm, marker, out_params = sys.argv[1:5]
    bbox = [float(x) for x in sys.argv[5:9]] if len(sys.argv) >= 9 else None

    if realm not in VALID_REALMS:
        print(f"preflight: FAIL invalid realm {realm!r}, expected one of {sorted(VALID_REALMS)}", file=sys.stderr)
        sys.exit(1)

    with open(input_csv) as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = REQUIRED_COLS - cols
        if missing:
            print(f"preflight: FAIL input missing required columns: {sorted(missing)}", file=sys.stderr)
            sys.exit(1)
        rows = list(reader)

    if not rows:
        print("preflight: FAIL input has zero data rows", file=sys.stderr)
        sys.exit(1)

    if bbox is None:
        lats = [float(r["decimalLatitude"]) for r in rows]
        lons = [float(r["decimalLongitude"]) for r in rows]
        pad = 0.25
        bbox = [min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad]

    params = {
        "skill_run": "edna-crosscheck",
        "realm": realm,
        "marker": marker,
        "bbox": bbox,
        "env_source": {"marine": "bio-oracle-v3", "freshwater": "worldclim-or-chelsa", "terrestrial": "worldclim-or-chelsa"},
        "env_layers": DEFAULT_ENV_LAYERS,
        "env_scenario": "present",
        "backbones": {"gbif": True, "worms": "marine-only", "fishbase": True},
        "obis_lookup": realm == "marine",
        "env_column_prefix": {"bio_oracle": "env_bio_", "worldclim_chelsa": "env_wc_"},
    }
    with open(out_params, "w") as f:
        json.dump(params, f, indent=2)
    print(f"preflight: GO realm={realm} rows={len(rows)} bbox={bbox} -> {out_params}")


if __name__ == "__main__":
    main()
