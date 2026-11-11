#!/usr/bin/env python3
"""occurrence_lookup: realm-routed corroboration source for OUT_OF_RANGE.

marine   -> GBIF occurrence/search + OBIS /occurrence  (independent corroboration)
freshwater/terrestrial -> GBIF occurrence/search only (PLAN §7 risk #9: single
                           source for non-marine realms; noted in the report)

Never called per-point: one geometry+taxonKey query per unique
(taxonKey-or-name, ring) pair, cached in-process for the run.

Usage: python3 occurrence_lookup.py <names_file> <routing.json> <params.json> <work_dir>
Writes: <work_dir>/occurrence_counts.json
        {scientificName: {"gbif": N_in_ring, "obis": N_in_ring|null,
                          "gbif_world": N_global, "obis_world": N_global|null}}

v2.5.2 GEODESIC ring semantics (was v2.5.1 box): the occurrence ring (--near-km R) is
BOTH the map ring and the concordance threshold, and it is now a GEODESIC CIRCLE with
CLIENT-SIDE haversine counting — the GBIF/OBIS occurrence-search endpoints have NO
reliable server-side distance predicate (geometry=WKT polygons degenerate on large
shapes: Abudefduf vaigiensis circle count returned 3 vs a true ~1100; distanceFrom-
CenterInMeter / geoDistance params are silently ignored), so records are fetched from
the cos(lat)-corrected bounding box (paginated, 300/1000 per page) and each record is
haversine-tested against R (R = 6371 km). The pre-2.5.2 axis-aligned box (± R/111° on
both axes) put box-corner points up to ~sqrt(2)·R km from the site inside the
threshold. Entries carry "ring_semantics": "geodesic-haversine" and, if the envelope
exceeded the fetch cap, "approximate": true (counts then remain box-based for that
species). World counts are unchanged.
Both sources are basisOfRecord-filtered (v1.0.2/v1.0.3): GBIF counts are exact
server-side filtered queries; OBIS counts are exact for any species with <=
OBIS_COUNT_FILTER_CAP raw records, an undercount above that (see netlog.
obis_filtered_count). "Beyond the ring" = world − ring. Consumers (viz, report) derive:
  CONCORDANT if ring count > 0 · DISCORDANT if ring == 0 but world > 0 ·
  NO_RECORD if world == 0 (absent from GBIF/OBIS everywhere we looked).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog, gbif_basis_of_record_qs, obis_filtered_count, obis_basis_of_record_ok  # noqa: E402
from geo import circle_wkt, corrected_box, haversine_km  # noqa: E402

GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
OBIS_OCC = "https://api.obis.org/v3/occurrence"


def _box_wkt(bbox: list[float]) -> str:
    """Box geometry as WKT POLYGON (used for the params region bbox and the
    antimeridian-corrected fallback box)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return (f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
            f"{min_lon} {max_lat},{min_lon} {min_lat}))")


MAX_FETCH_PER_SPECIES = 20000  # envelope fetch cap; beyond -> approximate=True

def gbif_records_in_geometry(net: NetLog, name: str, wkt: str, max_records: int = MAX_FETCH_PER_SPECIES):
    """All occurrence records inside a WKT geometry (paginated, GBIF caps pages at 300)."""
    out, offset, page = [], 0, 300
    while offset < max_records:
        url = (f"{GBIF_OCC}?scientificName={quote(name)}&geometry={quote(wkt)}"
               f"&limit={page}&offset={offset}{gbif_basis_of_record_qs()}")
        r = None
        try:
            r = net.get("gbif", url)
            r.raise_for_status()
            batch = r.json().get("results", [])
        except Exception:
            batch = []
        if not batch:
            break
        for x in batch:
            if x.get("decimalLatitude") is not None and x.get("decimalLongitude") is not None:
                out.append((x["decimalLongitude"], x["decimalLatitude"]))
        if r.json().get("endOfRecords"):
            break
        offset += len(batch)
    return out[:max_records]


def obis_records_in_geometry(net: NetLog, name: str, wkt: str, max_records: int = MAX_FETCH_PER_SPECIES):
    """All OBIS occurrence records inside a WKT geometry (paginated, size=1000)."""
    out, offset, page = [], 0, 1000
    while offset < max_records:
        url = (f"{OBIS_OCC}?scientificname={quote(name)}&geometry={quote(wkt)}"
               f"&size={page}&offset={offset}")
        r = None
        try:
            r = net.get("obis", url)
            r.raise_for_status()
            batch = r.json().get("results", [])
        except Exception:
            batch = []
        if not batch:
            break
        for x in batch:
            if x.get("decimalLatitude") is not None and x.get("decimalLongitude") is not None \
                    and obis_basis_of_record_ok(x.get("basisOfRecord")):
                out.append((x["decimalLongitude"], x["decimalLatitude"]))
        total = r.json().get("total") or 0
        offset += len(batch)
        if offset >= total or len(batch) == 0:
            break
    return out[:max_records]


def gbif_count(net: NetLog, name: str, wkt: str | None) -> int | None:
    """Exact GBIF occurrence count inside a WKT POLYGON. wkt=None -> worldwide count."""
    url = f"{GBIF_OCC}?scientificName={quote(name)}&limit=0{gbif_basis_of_record_qs()}"
    if wkt is not None:
        url += f"&geometry={quote(wkt)}"
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        return r.json().get("count")
    except Exception:
        return None


def obis_count(net: NetLog, name: str, wkt: str | None) -> int | None:
    """basisOfRecord-filtered OBIS occurrence count — see obis_filtered_count()."""
    url = f"{OBIS_OCC}?scientificname={quote(name)}"
    if wkt is not None:
        url += f"&geometry={quote(wkt)}"
    return obis_filtered_count(net, url)


def main() -> None:
    names_file, routing_path, params_path, work_dir = sys.argv[1:5]
    # optional 5th arg: ring_km (v2.5.2 geodesic ring) — when given, the primary
    # gbif/obis counts are server-side filtered to records WITHIN ring_km (geodesic
    # circle polygon); world counts are added either way.
    ring_km = float(sys.argv[5]) if len(sys.argv) > 5 else None
    work_dir = Path(work_dir)
    with open(routing_path) as f:
        routing = json.load(f)
    with open(params_path) as f:
        params = json.load(f)
    names = [n.strip() for n in Path(names_file).read_text().splitlines() if n.strip()]

    lon0, lat0 = params["input_extent"][0], params["input_extent"][1]
    if ring_km is not None:
        # v2.5.2: geodesic circle polygon (true-distance threshold). Antimeridian
        # fallback: lon-corrected box (cos(lat)), logged.
        ring_wkt = circle_wkt(lon0, lat0, ring_km)
        if ring_wkt is not None:
            count_wkt = ring_wkt
            print(f"occurrence-lookup: ring = geodesic circle R={ring_km:g} km "
                  f"(client-side haversine counts; envelope = cos(lat)-corrected box)")
        else:
            count_wkt = _box_wkt(corrected_box(lon0, lat0, ring_km))
            print("occurrence-lookup: WARNING ring crosses the antimeridian — "
                  "falling back to the cos(lat)-corrected bounding box", file=sys.stderr)
    else:
        count_wkt = _box_wkt(params["bbox"])

    # Read user_email from work_dir/params.json (preflight writes it there).


    params_p = work_dir / "params.json"


    if not params_p.exists():


        print("FAIL: " + str(params_p) + " missing — run preflight first.", file=sys.stderr)


        sys.exit(2)


    user_email = json.loads(params_p.read_text())["user_email"]


    net = NetLog(work_dir, user_email=user_email)
    out = {}
    for name in names:
        if ring_km is not None:
            # v2.5.2: exact geodesic ring count = fetch the cos(lat)-corrected envelope
            # records, haversine-test each against R. Envelope fetches that exceed the
            # cap fall back to the box WKT count (server-side) with approximate=true.
            env = corrected_box(lon0, lat0, ring_km)
            env_wkt = _box_wkt(env)
            pts = gbif_records_in_geometry(net, name, env_wkt)
            g_ring = sum(1 for lo, la in pts
                         if haversine_km(lon0, lat0, lo, la) <= ring_km)
            approximate = False
            if g_ring >= MAX_FETCH_PER_SPECIES * 0.95:
                approximate = True
                g_ring = gbif_count(net, name, env_wkt) or 0
            entry = {"gbif": g_ring, "gbif_world": gbif_count(net, name, None)}
            if routing.get("call_obis"):
                opts = obis_records_in_geometry(net, name, env_wkt)
                o_ring = sum(1 for lo, la in opts
                             if haversine_km(lon0, lat0, lo, la) <= ring_km)
                if o_ring >= MAX_FETCH_PER_SPECIES * 0.95:
                    approximate = True
                    o_ring = obis_count(net, name, env_wkt) or 0
                entry["obis"] = o_ring
            if approximate:
                entry["approximate"] = True
            entry["ring_semantics"] = ("geodesic-haversine (client-side; envelope fetch)"
                                       if not approximate else
                                       "geodesic-cap-exceeded: box WKT count (approximate)")
        else:
            # region counts (evidence pool) + world counts (merged-ring semantics: beyond = world - region)
            entry = {"gbif": gbif_count(net, name, count_wkt),
                     "gbif_world": gbif_count(net, name, None)}
            if routing.get("call_obis"):
                entry["obis"] = obis_count(net, name, count_wkt)
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
