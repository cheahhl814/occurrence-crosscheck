#!/usr/bin/env python3
"""context_records: fetch surrounding GBIF/OBIS occurrence RECORDS (not counts)
for each input species, for use as a regional "known-records" backdrop layer
under the detection points on occurrence maps.

Distinct from occurrence_lookup.py (counts only, limit=0): this fetches actual
records — capped per species (--per-species, default 150), within a --buffer-km
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
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
OBIS_OCC = "https://api.obis.org/v3/occurrence"


def records_gbif(net: NetLog, name: str, wkt: str, cap: int) -> list[dict]:
    url = (f"{GBIF_OCC}?scientificName={quote(name)}&geometry={quote(wkt)}"
           f"&limit={min(cap, 300)}&hasCoordinate=true")
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
                for x in r.json().get("results", []) if x.get("decimalLatitude") is not None]
    except Exception:
        return []


def main() -> None:
    input_csv, realm, params_path, work_dir = sys.argv[1:5]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    buffer_km = 500.0
    cap = 200
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
    out_csv = work.parent / ("candidates_context_occurrences.csv" if candidates_mode
                             else "context_occurrences.csv")

    params = json.loads(Path(params_path).read_text())
    extent = params.get("input_extent") or params["bbox"]
    pad = buffer_km / 111.0
    min_lon, min_lat, max_lon, max_lat = extent
    # context window: input extent + buffer (a REGION, not the tiny run bbox)
    ctx = [min_lon - pad, min_lat - pad, max_lon + pad, max_lat + pad]
    wkt = (f"POLYGON(({ctx[0]} {ctx[1]},{ctx[2]} {ctx[1]},{ctx[2]} {ctx[3]},"
           f"{ctx[0]} {ctx[3]},{ctx[0]} {ctx[1]}))")

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

    net = NetLog(work)
    out_rows, n_per = [], {}
    for name in names:
        gb = records_gbif(net, name, wkt, cap)
        ob = records_obis(net, name, wkt, cap) if call_obis else []
        # interleave and cap per species across sources
        merged = gb[:cap] + ob[:max(0, cap - len(gb))]
        n_per[name] = {"gbif": len(gb), "obis": len(ob), "kept": min(len(gb) + len(ob), cap)}
        out_rows.extend(merged)

    fieldnames = ["scientificName", "decimalLatitude", "decimalLongitude", "year", "source"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    total = sum(v["kept"] for v in n_per.values())
    print(f"context-records: {len(names)} species, buffer {buffer_km:.0f} km -> "
          f"{total} backdrop records ({sum(v['gbif'] for v in n_per.values())} gbif, "
          f"{sum(v['obis'] for v in n_per.values()) if call_obis else '-'} obis) -> {out_csv}")


if __name__ == "__main__":
    main()