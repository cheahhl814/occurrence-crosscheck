#!/usr/bin/env python3
"""occurrence_lookup: realm-routed corroboration source for OUT_OF_RANGE.

marine   -> GBIF occurrence/search + OBIS /occurrence  (independent corroboration)
freshwater/terrestrial -> GBIF occurrence/search only (PLAN §7 risk #9: single
                           source for non-marine realms; noted in the report)

Never called per-point: one bbox+taxonKey query per unique
(taxonKey-or-name, bbox) pair, cached in-process for the run.

Usage: python3 occurrence_lookup.py <names_file> <routing.json> <params.json> <work_dir>
Writes: <work_dir>/occurrence_counts.json  {scientificName: {"gbif": N, "obis": N|null}}
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
OBIS_OCC = "https://api.obis.org/v3/occurrence"


def gbif_count(net: NetLog, name: str, bbox: list[float]) -> int | None:
    min_lon, min_lat, max_lon, max_lat = bbox
    wkt = (f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
           f"{min_lon} {max_lat},{min_lon} {min_lat}))")
    url = f"{GBIF_OCC}?scientificName={quote(name)}&geometry={quote(wkt)}&limit=0"
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        return r.json().get("count")
    except Exception:
        return None


def obis_count(net: NetLog, name: str, bbox: list[float]) -> int | None:
    min_lon, min_lat, max_lon, max_lat = bbox
    geometry = (f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
                f"{min_lon} {max_lat},{min_lon} {min_lat}))")
    url = f"{OBIS_OCC}?scientificname={quote(name)}&geometry={quote(geometry)}&size=1"
    try:
        r = net.get("obis", url)
        r.raise_for_status()
        return r.json().get("total")
    except Exception:
        return None


def main() -> None:
    names_file, routing_path, params_path, work_dir = sys.argv[1:5]
    work_dir = Path(work_dir)
    with open(routing_path) as f:
        routing = json.load(f)
    with open(params_path) as f:
        params = json.load(f)
    names = [n.strip() for n in Path(names_file).read_text().splitlines() if n.strip()]

    net = NetLog(work_dir)
    out = {}
    for name in names:
        entry = {"gbif": gbif_count(net, name, params["bbox"])}
        if routing.get("call_obis"):
            entry["obis"] = obis_count(net, name, params["bbox"])
        else:
            entry["obis"] = None
        out[name] = entry

    out_path = work_dir / "occurrence_counts.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"occurrence-lookup: realm={routing['realm']} {len(names)} taxa -> {out_path}")


if __name__ == "__main__":
    main()
