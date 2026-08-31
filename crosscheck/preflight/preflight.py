#!/usr/bin/env python3
"""preflight: validate the input ASV/occurrence table + write the run
manifest (params.json contract, PLAN §11.1).

Required input columns (nf-edna ASV table / DwC-shaped occurrence table):
  scientificName, decimalLatitude, decimalLongitude, eventDate

Buffer zone (the corroboration window for OUT_OF_RANGE checks) is declared
here at preflight — three ways, precedence top-down:
  --bbox <minLon> <minLat> <maxLon> <maxLat>   explicit zone (wins)
  --buffer-km <N>                              pad input extent by N km
  (default)                                    pad input extent by 0.25 deg

The declared buffer is recorded in params.json (`buffer` block, PLAN §11.1)
so every downstream consumer (occurrence-lookup, crosscheck) uses the SAME
declared window and the report can state which window produced the verdicts.

Usage:
  python3 preflight.py <input.csv> <realm> <marker> <out_params.json> \
      [--bbox MINLON MINLAT MAXLON MAXLAT | --buffer-km N] [--buffer-deg D]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys

REQUIRED_COLS = {"scientificName", "decimalLatitude", "decimalLongitude", "eventDate"}
VALID_REALMS = {"marine", "freshwater", "terrestrial"}

DEFAULT_ENV_LAYERS = {
    "bio_oracle": ["thetao", "so"],
    "worldclim_chelsa": ["bio1", "bio12", "elev"],
}


def pad_deg_for_km(km: float, lat_extent: tuple[float, float]) -> float:
    """Degrees of longitude/lat padding equivalent to `km` — lon converted at the
    mean latitude of the input extent (cos(lat) shrink)."""
    lat_center = (lat_extent[0] + lat_extent[1]) / 2
    lat_deg = km / 111.0
    lon_deg = km / (111.0 * max(0.1, math.cos(math.radians(lat_center))))
    return max(lat_deg, lon_deg)


def main() -> None:
    ap = argparse.ArgumentParser(description="edna-crosscheck preflight")
    ap.add_argument("input_csv")
    ap.add_argument("realm", choices=sorted(VALID_REALMS))
    ap.add_argument("marker")
    ap.add_argument("out_params")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ap.add_argument("--buffer-km", type=float, default=None)
    ap.add_argument("--buffer-deg", type=float, default=None)
    args = ap.parse_args()

    n_bbox_opt = sum(x is not None for x in (args.bbox, args.buffer_km, args.buffer_deg))
    if n_bbox_opt > 1:
        print("preflight: FAIL use at most one of --bbox / --buffer-km / --buffer-deg", file=sys.stderr)
        sys.exit(1)

    with open(args.input_csv) as f:
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

    lats = [float(r["decimalLatitude"]) for r in rows]
    lons = [float(r["decimalLongitude"]) for r in rows]
    extent = [min(lons), min(lats), max(lons), max(lats)]

    if args.bbox is not None:
        bbox = [float(x) for x in args.bbox]
        buffer = {"mode": "user-bbox", "km": None, "pad_deg": None}
    elif args.buffer_km is not None:
        pad = pad_deg_for_km(args.buffer_km, (min(lats), max(lats)))
        bbox = [extent[0] - pad, extent[1] - pad, extent[2] + pad, extent[3] + pad]
        buffer = {"mode": "user-km", "km": args.buffer_km, "pad_deg": round(pad, 4)}
    elif args.buffer_deg is not None:
        bbox = [extent[0] - args.buffer_deg, extent[1] - args.buffer_deg,
                extent[2] + args.buffer_deg, extent[3] + args.buffer_deg]
        buffer = {"mode": "user-deg", "km": None, "pad_deg": args.buffer_deg}
    else:
        pad = 0.25
        bbox = [extent[0] - pad, extent[1] - pad, extent[2] + pad, extent[3] + pad]
        buffer = {"mode": "auto", "km": None, "pad_deg": pad}

    params = {
        "skill_run": "edna-crosscheck",
        "realm": args.realm,
        "marker": args.marker,
        "bbox": bbox,
        "input_extent": extent,
        "buffer": buffer,
        "env_source": {"marine": "bio-oracle-v3", "freshwater": "worldclim-or-chelsa", "terrestrial": "worldclim-or-chelsa"},
        "env_layers": DEFAULT_ENV_LAYERS,
        "env_scenario": "present",
        "backbones": {"gbif": True, "worms": "marine-only", "fishbase": True},
        "obis_lookup": args.realm == "marine",
        "env_column_prefix": {"bio_oracle": "env_bio_", "worldclim_chelsa": "env_wc_"},
    }
    with open(args.out_params, "w") as f:
        json.dump(params, f, indent=2)
    print(f"preflight: GO realm={args.realm} rows={len(rows)} extent={extent} "
          f"buffer={buffer['mode']}({buffer.get('pad_deg', 0) if buffer['mode'] != 'user-bbox' else 'explicit'}) "
          f"bbox={bbox} -> {args.out_params}")


if __name__ == "__main__":
    main()