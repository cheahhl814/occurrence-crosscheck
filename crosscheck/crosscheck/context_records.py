#!/usr/bin/env python3
"""context_records: fetch surrounding GBIF/OBIS occurrence RECORDS (not counts)
for each input species, for use as a regional "known-records" backdrop layer
under the detection points on occurrence maps.

Distinct from occurrence_lookup.py (counts only, limit=0): this fetches actual
records — capped per species (--per-species, default 150), within a --buffer-km
ring, PLUS (v2.5.1, --outside-cap N) a bounded global sample BEYOND the ring so maps
can show where species occur outside it. v2.5.2: for a single-site (degenerate)
input extent the window is a GEODESIC CIRCLE (server-side polygon filter + client
haversine double-check), matching occurrence_lookup v2.5.2; multi-site extents keep
the box window with a cos(lat)-corrected longitude pad:
region (default 500 km) around the input extent. "Database sampling gap at a
tiny buffer" is exactly the failure 2024K1 exposed, so the context window is
wider than the crosscheck window BY DEFAULT.

Usage:
  context_records.py <input.csv> <realm> <params.json> <work_dir> \
      [--buffer-km 500] [--per-species 200]

Writes: <work_dir or --out>/context_occurrences.csv
        (scientificName, decimalLatitude, decimalLongitude, source, year)
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog, gbif_basis_of_record_qs, obis_basis_of_record_ok  # noqa: E402
from geo import circle_wkt, corrected_box, haversine_km  # noqa: E402

def _box_wkt(bbox: list[float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    return (f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
            f"{min_lon} {max_lat},{min_lon} {min_lat}))")


GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
OBIS_OCC = "https://api.obis.org/v3/occurrence"


def records_gbif(net: NetLog, name: str, wkt: str, cap: int) -> list[dict]:
    url = (f"{GBIF_OCC}?scientificName={quote(name)}&geometry={quote(wkt)}"
           f"&limit={min(cap, 300)}&hasCoordinate=true{gbif_basis_of_record_qs()}")
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        return [{"scientificName": name, "decimalLatitude": x["decimalLatitude"],
                 "decimalLongitude": x["decimalLongitude"],
                 "year": x.get("year") or "", "source": "gbif"}
                for x in r.json().get("results", [])]
    except Exception:
        return []


def records_obis(net: NetLog, name: str, wkt: str, cap: int) -> list[dict]:
    url = (f"{OBIS_OCC}?scientificname={quote(name)}&geometry={quote(wkt)}"
           f"&size={min(cap, 300)}")
    try:
        r = net.get("obis", url)
        r.raise_for_status()
        return [{"scientificName": x.get("scientificName", name),
                 "decimalLatitude": x["decimalLatitude"], "decimalLongitude": x["decimalLongitude"],
                 "year": (x.get("eventDate") or "")[:4], "source": "obis"}
                for x in r.json().get("results", [])
                if x.get("decimalLatitude") is not None and obis_basis_of_record_ok(x.get("basisOfRecord"))]
    except Exception:
        return []


def records_gbif_global(net: NetLog, name: str, cap: int) -> list[dict]:
    """Global (no geometry) GBIF sample for a taxon — the beyond-ring display pool."""
    url = f"{GBIF_OCC}?scientificName={quote(name)}&limit={min(cap, 300)}{gbif_basis_of_record_qs()}"
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        return [
            {
                "scientificName": name,
                "decimalLatitude": (x.get("decimalLatitude") if isinstance(x, dict) else None),
                "decimalLongitude": (x.get("decimalLongitude") if isinstance(x, dict) else None),
                "year": (x.get("year") or "") if isinstance(x, dict) else "",
                "source": "gbif",
            }
            for x in r.json().get("results", [])
            if isinstance(x, dict) and x.get("decimalLatitude") is not None
        ]
    except Exception:
        return []


def records_obis_global(net: NetLog, name: str, cap: int) -> list[dict]:
    """Global (no geometry) OBIS sample for a taxon."""
    url = f"{OBIS_OCC}?scientificname={quote(name)}&size={min(cap, 250)}"
    try:
        r = net.get("obis", url)
        r.raise_for_status()
        return [
            {"scientificName": x.get("scientificName", name),
             "decimalLatitude": x["decimalLatitude"], "decimalLongitude": x["decimalLongitude"],
             "year": (x.get("eventDate") or x.get("year") or "")[:4] if isinstance(x.get("eventDate") or x.get("year") or "", str) else "",
             "source": "obis"}
            for x in r.json().get("results", [])
            if x.get("decimalLatitude") is not None and obis_basis_of_record_ok(x.get("basisOfRecord"))
        ]
    except Exception:
        return []


def main() -> None:
    input_csv, realm, params_path, work_dir = sys.argv[1:5]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    buffer_km = 500.0
    cap = 200
    outside_cap = 0
    # --candidates <genus_candidates.csv> (v2.4.0): fetch backdrop records for the
    # predicted (genus-narrow) candidate species instead of the detected taxa
    argv = sys.argv[5:]
    candidates_mode = "--candidates" in argv
    candidates_path = None
    if candidates_mode:
        i = argv.index("--candidates")
        candidates_path = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if "--buffer-km" in argv:
        buffer_km = float(argv[argv.index("--buffer-km") + 1])
    if "--per-species" in argv:
        cap = int(argv[argv.index("--per-species") + 1])
    if "--outside-cap" in argv:
        outside_cap = int(argv[argv.index("--outside-cap") + 1])
    out_csv = work.parent / ("candidates_context_occurrences.csv" if candidates_mode
                             else "context_occurrences.csv")

    params = json.loads(Path(params_path).read_text())
    extent = params.get("input_extent") or params["bbox"]
    min_lon, min_lat, max_lon, max_lat = extent
    # v2.5.2: single-site extent -> GEODESIC CIRCLE window (matches the verdict
    # threshold exactly); degenerate = single (lat, site) point. Multi-site extents
    # keep the box window with a cos(lat)-corrected longitude pad.
    if min_lon == max_lon and min_lat == max_lat:
        site_lon, site_lat = min_lon, min_lat
        # GBIF/OBIS server-side geometry=WKT degenerates on large polygons (GBIF
        # circle query returned 3 of a true ~1100 for Abudefduf vaigiensis at R=2000),
        # so fetch the cos(lat)-corrected BOX and let the client haversine filter
        # decide in-ring vs beyond-ring; the window mode name documents that chain.
        ctx = corrected_box(site_lon, site_lat, buffer_km)
        wkt = _box_wkt(ctx)
        window_mode = "geodesic-client (corrected-box fetch + haversine filter)"
    else:
        site_lon, site_lat = (min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0
        lat_pad = buffer_km / 111.0
        lon_pad = buffer_km / (111.0 * max(0.05, __import__("math").cos(
            __import__("math").radians((min_lat + max_lat) / 2.0))))
        ctx = [min_lon - lon_pad, min_lat - lat_pad, max_lon + lon_pad, max_lat + lat_pad]
        wkt = _box_wkt(ctx)
        window_mode = "corrected-box (multi-site extent)"
    print(f"context-records: window = {window_mode} "
          f"(buffer {buffer_km:g} km; in-ring rows pass a haversine double-check)")

    if candidates_mode:
        cand_binoms = {}
        for r in csv.DictReader(open(candidates_path, newline="")):
            display = (r.get("candidate_species") or "").strip()
            if display:
                binom = " ".join(display.split()[:2])  # strip author citation
                cand_binoms[binom] = True
        names = sorted(cand_binoms)
    else:
        with open(input_csv, newline="") as f:
            names = sorted({r["scientificName"].strip() for r in csv.DictReader(f) if r.get("scientificName")})

    call_obis = realm == "marine"  # realm-router rule, mirrored here without routing.json

    # Read user_email from work_dir/params.json (preflight writes it there).


    params_p = work / "params.json"


    if not params_p.exists():


        print("FAIL: " + str(params_p) + " missing — run preflight first.", file=sys.stderr)


        sys.exit(2)


    user_email = json.loads(params_p.read_text())["user_email"]


    net = NetLog(work, user_email=user_email)
    out_rows, n_per, n_out = [], {}, {}
    for name in names:
        gb = records_gbif(net, name, wkt, cap)
        ob = records_obis(net, name, wkt, cap) if call_obis else []
        merged = gb[:cap] + ob[:max(0, cap - len(gb))]
        # v2.5.2 geodesic double-check (circle mode): drop any server-returned row
        # haversine-farther than the ring (geo_shape predicates are approximate)
        if window_mode == "geodesic-circle":
            before = len(merged)
            merged = [r for r in merged
                      if haversine_km(site_lon, site_lat, r["decimalLongitude"],
                                      r["decimalLatitude"]) <= buffer_km]
            drop_note = before - len(merged)
        else:
            drop_note = 0
        n_per[name] = {"gbif": len(gb), "obis": len(ob), "kept": len(merged),
                       "haversine_dropped": drop_note}
        out_rows.extend(merged)

        # v2.5.1 merged-ring semantics: bounded GLOBAL sample beyond the context window,
        # so maps can show where a species occurs outside the ring (DISCORDANT narrative)
        # and NO_RECORD means "absent from GBIF/OBIS everywhere we looked".
        if outside_cap > 0:
            gbw = records_gbif_global(net, name, outside_cap)
            obw = records_obis_global(net, name, outside_cap) if call_obis else []
            # keep only rows outside the in-window bbox (those are already covered above)
            if window_mode == "geodesic-circle":
                outs = [r for r in gbw + obw
                        if r["decimalLatitude"] is not None and r["decimalLongitude"] is not None
                        and haversine_km(site_lon, site_lat, r["decimalLongitude"],
                                         r["decimalLatitude"]) > buffer_km][:outside_cap]
            else:
                outs = [r for r in gbw + obw
                        if r["decimalLatitude"] is not None and r["decimalLongitude"] is not None
                        and not (ctx[0] <= r["decimalLongitude"] <= ctx[2]
                                 and ctx[1] <= r["decimalLatitude"] <= ctx[3])][:outside_cap]
            n_out[name] = len(outs)
            out_rows.extend(outs)

    fieldnames = ["scientificName", "decimalLatitude", "decimalLongitude", "year", "source"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    total = sum(v["kept"] for v in n_per.values())
    out_total = sum(n_out.values()) if outside_cap > 0 else 0
    drops = sum(v.get("haversine_dropped", 0) for v in n_per.values())
    print(f"context-records [{window_mode}]" + (f" haversine-dropped {drops}" if drops else "") + f": {len(names)} species, buffer {buffer_km:.0f} km -> "
          f"{total} backdrop records ({sum(v['gbif'] for v in n_per.values())} gbif, "
          f"{sum(v['obis'] for v in n_per.values()) if call_obis else '-'} obis) "
          f"+ {out_total} beyond-window sample records (outside_cap={outside_cap}) -> {out_csv}")


if __name__ == "__main__":
    main()