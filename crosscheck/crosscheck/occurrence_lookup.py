#!/usr/bin/env python3
"""occurrence_lookup: realm-routed corroboration source for OUT_OF_RANGE.

marine   -> GBIF occurrence/search + OBIS /occurrence  (independent corroboration)
freshwater/terrestrial -> GBIF occurrence/search only (PLAN §7 risk #9: single
                           source for non-marine realms; noted in the report)

Never called per-point: one bbox+taxonKey query per unique
(taxonKey-or-name, bbox) pair, cached in-process for the run.

Usage: python3 occurrence_lookup.py <names_file> <routing.json> <params.json> <work_dir>
Writes: <work_dir>/occurrence_counts.json
        {scientificName: {"gbif": N_in_region, "obis": N_in_region|null,
                          "gbif_world": N_global, "obis_world": N_global|null}}

v2.5.1 merged-ring semantics (PLAN §11.13): the occurrence ring (--near-km R) is BOTH the
map ring and the concordance threshold. Counts are computed twice per source: within the
region bbox (in-ring evidence) and globally (world). Both are basisOfRecord-filtered (v1.0.2/
v1.0.3): GBIF counts are exact server-side filtered queries; OBIS counts are exact for any
species with <= OBIS_COUNT_FILTER_CAP raw records, an undercount above that (see
netlog.obis_filtered_count). "Beyond the ring" = world − region. Consumers (viz, report) derive:
  CONCORDANT if region count > 0 · DISCORDANT if region == 0 but world > 0 ·
  NO_RECORD if world == 0 (absent from GBIF/OBIS everywhere we looked).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog, gbif_basis_of_record_qs, obis_filtered_count  # noqa: E402

GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
OBIS_OCC = "https://api.obis.org/v3/occurrence"


def gbif_count(net: NetLog, name: str, bbox: list[float] | None) -> int | None:
    """Exact GBIF occurrence count. bbox=None -> worldwide count (no geometry filter)."""
    url = f"{GBIF_OCC}?scientificName={quote(name)}&limit=0{gbif_basis_of_record_qs()}"
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        wkt = (f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
               f"{min_lon} {max_lat},{min_lon} {min_lat}))")
        url += f"&geometry={quote(wkt)}"
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        return r.json().get("count")
    except Exception:
        return None


def obis_count(net: NetLog, name: str, bbox: list[float] | None) -> int | None:
    """basisOfRecord-filtered OBIS occurrence count — see obis_filtered_count()."""
    url = f"{OBIS_OCC}?scientificname={quote(name)}"
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        geometry = (f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
                    f"{min_lon} {max_lat},{min_lon} {min_lat}))")
        url += f"&geometry={quote(geometry)}"
    return obis_filtered_count(net, url)


def main() -> None:
    names_file, routing_path, params_path, work_dir = sys.argv[1:5]
    # optional 5th arg: ring_km (v2.5.1 merged-ring) — when given, the primary
    # gbif/obis counts are computed within the RING bbox (input_extent ± ring) rather
    # than the params region bbox; world counts are added either way.
    ring_km = float(sys.argv[5]) if len(sys.argv) > 5 else None
    work_dir = Path(work_dir)
    with open(routing_path) as f:
        routing = json.load(f)
    with open(params_path) as f:
        params = json.load(f)
    names = [n.strip() for n in Path(names_file).read_text().splitlines() if n.strip()]

    if ring_km is not None:
        lon0, lat0 = params["input_extent"][0], params["input_extent"][1]
        pad = ring_km / 111.0
        count_bbox = [lon0 - pad, lat0 - pad, lon0 + pad, lat0 + pad]
    else:
        count_bbox = params["bbox"]

    net = NetLog(work_dir)
    out = {}
    for name in names:
        # region counts (evidence pool) + world counts (merged-ring semantics: beyond = world - region)
        entry = {"gbif": gbif_count(net, name, count_bbox),
                 "gbif_world": gbif_count(net, name, None)}
        if routing.get("call_obis"):
            entry["obis"] = obis_count(net, name, count_bbox)
            entry["obis_world"] = obis_count(net, name, None)
        else:
            entry["obis"] = None
            entry["obis_world"] = None
        out[name] = entry

    out_path = work_dir / "occurrence_counts.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"occurrence-lookup: realm={routing['realm']} {len(names)} taxa -> {out_path}")


if __name__ == "__main__":
    main()
