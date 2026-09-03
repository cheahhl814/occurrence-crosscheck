#!/usr/bin/env python3
"""checklist_builder: MODE B inverted query — coordinates -> expected species.

For each input point (work/points.csv from input_adapters, coords mode), builds
a buffered-square geometry (radius from params.json bbox padding or --radius)
and queries the realm-routed occurrence sources for the taxa expected there:

  marine    -> OBIS /v3/checklist (taxa + counts) AND GBIF occurrence/search
               facet=scientificName (redundant corroboration per PLAN §4)
  non-marine-> GBIF occurrence/search facet only (PLAN §7 risk #9)

Emits work/names.txt (union of expected taxa, feeding the standard
taxon-resolve -> fishbase-traits chain) + work/checklist_raw.json
(per-point expected taxa with counts).

Usage: checklist_builder.py <points_csv> <routing_json> <params_json> <work_dir> [max_taxa_per_point]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

OBIS_CHECKLIST = "https://api.obis.org/v3/checklist"
GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"


def _square(lat: float, lon: float, radius: float) -> str:
    wkt = (f"POLYGON(({lon - radius} {lat - radius},{lon + radius} {lat - radius},"
           f"{lon + radius} {lat + radius},{lon - radius} {lat + radius},{lon - radius} {lat - radius}))")
    return wkt


def obis_checklist(net: NetLog, wkt: str, max_taxa: int, realm: str = "marine") -> list[dict]:
    """OBIS /v3/checklist returns {total, results:[{scientificName, aphia(?), count,
    is_marine, is_brackish, is_freshwater, is_terrestrial, ...}]} — use the WoRMS
    environment flags to pre-filter by realm (keeps e.g. birds out of marine checklists)."""
    realm_flag = {"marine": ("is_marine", "is_brackish"),
                  "freshwater": ("is_freshwater", "is_brackish"),
                  "terrestrial": ("is_terrestrial",)}[realm]
    url = f"{OBIS_CHECKLIST}?geometry={quote(wkt)}"
    try:
        r = net.get("obis", url)
        r.raise_for_status()
        d = r.json()
        results = d.get("results") or []
        results.sort(key=lambda t: -int(t.get("count", 0) or 0))
        out = []
        for t in results:
            if not t.get("scientificName"):
                continue
            if not any(t.get(flag) for flag in realm_flag):
                continue
            out.append({"name": t["scientificName"], "aphia": t.get("acceptedNameUsageID") or t.get("taxonID"),
                        "n_records": t.get("count")})
            if len(out) >= max_taxa:
                break
        return out
    except Exception:
        return []


def gbif_facet_species(net: NetLog, wkt: str, max_taxa: int) -> list[dict]:
    url = f"{GBIF_OCC}?geometry={quote(wkt)}&limit=0&facet=scientificName&facetLimit={max_taxa}"
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        facets = r.json().get("facets") or []
        counts = facets[0].get("counts", []) if facets else []
        return [{"name": c.get("name", ""), "n_records": c.get("count")} for c in counts if c.get("name")]
    except Exception:
        return []


def main() -> None:
    points_csv, routing_path, params_path, work_dir = sys.argv[1:5]
    max_taxa = int(sys.argv[5]) if len(sys.argv) >= 6 else 200
    work = Path(work_dir)
    routing = json.loads(Path(routing_path).read_text())
    params = json.loads(Path(params_path).read_text())

    # radius recovered from how the bbox was padded by input_adapters (kept symmetric)
    with open(points_csv) as f:
        points = list(csv.DictReader(f))
    min_lon, min_lat, max_lon, max_lat = params["bbox"]
    # padding symmetry: radius = half the width the adapter added (default 0.5 re-derived
    # from the bbox is ambiguous with multiple points, so radius is the mean pad)
    radius = max(0.05, ((max_lon - min_lon) + (max_lat - min_lat)) / 4)

    # Read user_email from work_dir/params.json (preflight writes it there).


    params_p = work / "params.json"


    if not params_p.exists():


        print("FAIL: " + str(params_p) + " missing — run preflight first.", file=sys.stderr)


        sys.exit(2)


    user_email = json.loads(params_p.read_text())["user_email"]


    net = NetLog(work, user_email=user_email)
    raw: dict[str, dict] = {}
    union: set[str] = set()
    for p in points:
        lat, lon = float(p["decimalLatitude"]), float(p["decimalLongitude"])
        wkt = _square(lat, lon, radius)
        entry = {"point_id": p["point_id"], "radius_deg": round(radius, 3)}
        if routing.get("call_obis"):
            entry["obis_taxa"] = obis_checklist(net, wkt, max_taxa, realm=routing["realm"])
        else:
            entry["obis_taxa"] = None
        entry["gbif_taxa"] = gbif_facet_species(net, wkt, max_taxa)
        for t in (entry["obis_taxa"] or []) + entry["gbif_taxa"]:
            if t["name"]:
                union.add(t["name"])
        raw[p["point_id"]] = entry

    (work / "names.txt").write_text("\n".join(sorted(union)) + "\n")
    (work / "checklist_raw.json").write_text(json.dumps(raw, indent=2))
    print(f"checklist-builder: {len(points)} points, {len(union)} union taxa -> {work}/names.txt")


if __name__ == "__main__":
    main()