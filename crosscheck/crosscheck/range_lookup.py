#!/usr/bin/env python3
"""range_lookup: MODE A inverted query — the occurrence envelope IS the output.

For each species (already resolved by taxon-resolve, traits joined by
fishbase-traits), reports its KNOWN range instead of checking a detection
against one:

  - global occurrence counts (GBIF always; OBIS for marine realms, per routing)
  - empirical extent: bbox computed from a sample of georeferenced GBIF records
    (up to --record_limit per species, default 120)
  - FishBase trait envelope (depth range, trophic level, body size)

Realm routing is honored via routing.json: OBIS is only called when
routing["call_obis"] is true (marine). No bbox filtering anywhere — the global
extent is what mode A is for.

Usage: range_lookup.py <names_file> <routing.json> <work_dir> [record_limit]
Writes: species_envelopes.csv next to work_dir; species_raw.json inside work_dir.
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


def gbif_records(net: NetLog, name: str, limit: int) -> tuple[int | None, list[dict]]:
    """(global count, sampled georeferenced records) — no geometry filter."""
    url = f"{GBIF_OCC}?scientificName={quote(name)}&limit={limit}&hasCoordinate=true"
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        d = r.json()
        recs = [{"decimalLatitude": x["decimalLatitude"], "decimalLongitude": x["decimalLongitude"],
                 "year": x.get("year")}
                for x in d.get("results", [])
                if x.get("decimalLatitude") is not None and x.get("decimalLongitude") is not None]
        return d.get("count"), recs
    except Exception:
        return None, []


def obis_count(net: NetLog, name: str) -> int | None:
    url = f"{OBIS_OCC}?scientificname={quote(name)}&size=0"
    try:
        r = net.get("obis", url)
        r.raise_for_status()
        return r.json().get("total")
    except Exception:
        return None


def envelope(recs: list[dict]) -> dict:
    if not recs:
        return {"gbif_extent_bbox": "", "gbif_extent_n": 0}
    lats = [r["decimalLatitude"] for r in recs]
    lons = [r["decimalLongitude"] for r in recs]
    return {"gbif_extent_bbox": json.dumps([round(min(lons), 3), round(min(lats), 3),
                                            round(max(lons), 3), round(max(lats), 3)]),
            "gbif_extent_n": len(recs)}


def main() -> None:
    names_file, routing_path, work_dir = sys.argv[1:4]
    limit = int(sys.argv[4]) if len(sys.argv) >= 5 else 120
    work = Path(work_dir)
    out_dir = work.parent
    routing = json.loads(Path(routing_path).read_text())
    names = [n.strip() for n in Path(names_file).read_text().splitlines() if n.strip()]

    fb_path = work / "fishbase_pull.json"
    fb = json.loads(fb_path.read_text() or "{}") if fb_path.exists() else {}
    if isinstance(fb, list):  # fishbase_traits emits [] when nothing resolved
        fb = {d.get("scientificName") or d.get("Scientical", d.get("ScientificName", "")): d
              for d in fb if isinstance(d, dict)}

    crosswalk_resolve_note = work / "review_queue.csv"  # taxon-resolve wrote it; carry through downstream
    net = NetLog(work)
    rows = []
    for name in names:
        fb_e = fb.get(name, {})
        count, recs = gbif_records(net, name, limit)
        row = {
            "scientificName": name,
            "gbif_global_records": count,
            "obis_global_records": obis_count(net, name) if routing.get("call_obis") else None,
            "trait_depth_min_m": fb_e.get("DepthRangeShallow", ""),
            "trait_depth_max_m": fb_e.get("DepthRangeDeep", ""),
            "trait_body_size_cm": fb_e.get("Length", ""),
            "trait_trophic_level": fb_e.get("trophic_level", ""),
        }
        row.update(envelope(recs))
        rows.append(row)

    fieldnames = sorted({k for r in rows for k in r})
    out_csv = out_dir / "species_envelopes.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    (out_dir / "review_queue.csv").write_text(crosswalk_resolve_note.read_text()) if crosswalk_resolve_note.exists() else None
    (work / "species_raw.json").write_text(json.dumps(rows, indent=2))
    print(f"range-lookup: {len(names)} species -> {out_csv}")


if __name__ == "__main__":
    main()