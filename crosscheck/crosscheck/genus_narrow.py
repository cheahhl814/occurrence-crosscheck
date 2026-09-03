#!/usr/bin/env python3
"""genus_narrow: narrow genus-only ASVs to candidate species using regional occurrence records.

For each genus (from ASVs identified only to genus, e.g. idtaxa "Sillago" /
"Sillago sp."), queries the realm-routed occurrence sources for WHICH species
OF THAT GENUS are recorded within the declared buffer around the detection
site(s), and ranks candidates by regional corroboration:

  gbif   -> /v1/species/match (genusKey) then occurrence/search
            taxonKey=<genusKey>&facet=scientificName (species of the genus in-buffer)
  obis    -> /v3/checklist (realm-flag-filtered, marine only),
             results filtered to names under "<genus> " (WoRMS environment
             flags from PLAN scope apply)

Ranking: total corroborating records in-buffer, descending (per species across
all sources). Compatibility with FishBase depth is annotated when fishbase_pull
is available, but is NOT a filter (traits stay advisory per skill policy).

Usage:
  genus_narrow.py <input.csv> <realm> <out_dir> [--buffer-km N | radius via bbox pad 0.5]
    input.csv : scientificName ("Genus sp." or plain "Genus"; species suffixes are
                stripped), optional decimalLatitude,decimalLongitude (required:
                at least one of the two columns, or all rows share the first point)

Writes: genus_candidates.csv, review_queue.csv (passthrough), params.json, work/
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # checklist_builder
from netlog import NetLog  # noqa: E402

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"


def clean_genus(name: str) -> str:
    """'Sillago sp. 2 SS-2021' / 'Sillago' / 'Sillago sihama' -> 'Sillago'."""
    return name.strip().split()[0].rstrip(",;")


def gbif_genus_key(net: NetLog, genus: str) -> int | None:
    try:
        r = net.get("gbif", f"{GBIF_MATCH}?name={quote(genus)}&rank=GENUS")
        r.raise_for_status()
        d = r.json()
        if d.get("rank") == "GENUS" and d.get("genusKey"):
            return d["genusKey"]
        return d.get("genusKey")  # match may land on a species of that genus
    except Exception:
        return None


def gbif_species_in_genus(net: NetLog, genus_key: int, wkt: str, max_sp: int) -> list[dict]:
    url = (f"{GBIF_OCC}?taxonKey={genus_key}&geometry={quote(wkt)}&limit=0"
           f"&facet=speciesKey&facet=scientificName&facetLimit={max_sp}")
    try:
        r = net.get("gbif", url)
        r.raise_for_status()
        facets = r.json().get("facets") or []
        # speciesKey facet (counts), scientificName facet (names) — pair by index
        keys = facets[0].get("counts", []) if facets else []
        names = facets[1].get("counts", []) if len(facets) > 1 else []
        out = []
        for i, k in enumerate(keys):
            nm = names[i].get("name", "") if i < len(names) else ""
            if not nm or nm.startswith("  ") or ":" in nm:
                continue  # blank open-nomenclature + BOLD:<BIN> placeholder taxa
            parts = nm.split()
            if len(parts) >= 2 and parts[0] == nm.split(" ")[0] and parts[1][:1].isupper():
                continue  # author-citation on a genus-rank occurrence ('Sillago Cuvier, 1816')
            out.append({"name": nm, "n_records": int(k.get("count", 0) or 0)})
        return out
    except Exception:
        return []


def obis_species_in_genus(net: NetLog, genus: str, wkt: str, realm: str) -> list[dict]:
    """OBIS checklist per geometry, filtered to names under '<genus> '."""
    obis_checklist = "https://api.obis.org/v3/checklist"
    realm_flag = {"marine": ("is_marine", "is_brackish"),
                  "freshwater": ("is_freshwater", "is_brackish"),
                  "terrestrial": ("is_terrestrial",)}[realm]
    url = f"{obis_checklist}?geometry={quote(wkt)}"
    try:
        r = net.get("obis", url)
        r.raise_for_status()
        results = r.json().get("results") or []
        out = []
        for t in results:
            nm = t.get("scientificName", "") or ""
            if not nm.startswith(f"{genus} "):
                continue
            if not any(t.get(flag) for flag in realm_flag):
                continue
            out.append({"name": nm, "n_records": int(t.get("count", 0) or 0)})
        return out
    except Exception:
        return []


def main() -> None:
    argv = sys.argv[1:]
    # SP-4: --user-email is mandatory (same contract as preflight/preflight.py
    # + input_adapters.py). Required by NetLog for GBIF/OBIS API contact.
    if "--user-email" in argv:
        i = argv.index("--user-email")
        try:
            user_email = argv[i + 1]
        except IndexError:
            raise SystemExit("genus_narrow: FAIL --user-email requires a value")
        argv = argv[:i] + argv[i + 2:]
    elif any(a.startswith("--user-email=") for a in argv):
        for a in argv:
            if a.startswith("--user-email="):
                user_email = a.split("=", 1)[1]
                argv.remove(a)
                break
    else:
        raise SystemExit(
            "genus_narrow: FAIL --user-email is required (SP-4 — GBIF/OBIS API contact-attribution policy). "
            "Re-run with --user-email <address>."
        )
    if not _EMAIL_RE.match(user_email):
        raise SystemExit(
            f"genus_narrow: FAIL --user-email {user_email!r} does not look like an email address. "
            f"Re-ask the user for a valid local@domain.tld value."
        )
    input_csv, realm, out_dir = argv[0:3]
    buffer_km = float(argv[3]) if len(argv) >= 4 else 0.0
    max_sp = int(argv[4]) if len(argv) >= 5 else 40

    if realm not in {"marine", "freshwater", "terrestrial"}:
        raise SystemExit(f"genus_narrow: FAIL invalid realm {realm!r}")
    out = Path(out_dir)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    with open(input_csv) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("genus_narrow: FAIL zero input rows")

    # genera + detection sites
    lat_keys = ("decimalLatitude", "lat", "latitude")
    lon_keys = ("decimalLongitude", "lon", "long", "longitude")

    def col(row, keys):
        low = {k.strip().lower(): v for k, v in row.items()}
        for k in keys:
            v = low.get(k.lower())
            if v is not None and str(v).strip():
                return str(v).strip()
        return None

    genera: dict[str, list[tuple[float, float]]] = {}
    for i, r in enumerate(rows):
        name = (r.get("scientificName") or r.get("taxon") or "").strip()
        if not name:
            raise SystemExit(f"genus_narrow: FAIL row {i + 1} missing scientificName")
        g = clean_genus(name)
        lat, lon = col(r, lat_keys), col(r, lon_keys)
        pts = genera.setdefault(g, [])
        if lat and lon:
            pts.append((float(lat), float(lon)))
        elif not pts:  # no coords anywhere for this genus -> error
            raise SystemExit(
                f"genus_narrow: FAIL no coordinates for genus {g!r} and no --center; "
                "genus narrowing is inherently regional and needs a detection site or --bbox")

    # Read user_email from work_dir/params.json (preflight writes it there).


    params_p = work / "params.json"


    if not params_p.exists():


        print("FAIL: " + str(params_p) + " missing — run preflight first.", file=sys.stderr)


        sys.exit(2)


    user_email = json.loads(params_p.read_text())["user_email"]


    net = NetLog(work, user_email=user_email)
    out_rows = []
    for genus, pts in genera.items():
        seen_points = sorted(set(pts)) or [(None, None)]
        cache: dict[int, list[dict]] = {}
        per_genus: dict[str, dict] = {}
        for lat, lon in seen_points:
            lat, lon = lat or 0.0, lon or 0.0
            if buffer_km > 0:
                pad = buffer_km / 111.0
            else:
                pad = 0.5
            wkt = (f"POLYGON(({lon - pad} {lat - pad},{lon + pad} {lat - pad},"
                   f"{lon + pad} {lat + pad},{lon - pad} {lat + pad},{lon - pad} {lat - pad}))")
            gk = gbif_genus_key(net, genus)
            for t in gbif_species_in_genus(net, gk, wkt, max_sp) if gk else []:
                e = per_genus.setdefault(t["name"], {"source": set(), "n": 0, "speciesKey": None})
                e["n"] += t["n_records"]
                e["source"].add("gbif")
            if realm == "marine":
                for t in obis_species_in_genus(net, genus, wkt, realm):
                    e = per_genus.setdefault(t["name"], {"source": set(), "n": 0, "speciesKey": None})
                    e["n"] += t["n_records"]
                    e["source"].add("obis")
        ranked = sorted(per_genus.items(), key=lambda kv: -kv[1]["n"])
        for rank, (nm, e) in enumerate(ranked[:max_sp], start=1):
            out_rows.append({
                "genus": genus, "candidate_species": nm, "rank": rank,
                "n_records_in_buffer": e["n"],
                "sources": ",".join(sorted(e["source"])),
                "n_detection_sites": len(seen_points),
                "buffer_km": buffer_km if buffer_km > 0 else f"{pad*111:.1f}(defaultdeg)",
            })

    fieldnames = ["genus", "candidate_species", "rank", "n_records_in_buffer", "sources",
                  "n_detection_sites", "buffer_km"]
    with open(out / "genus_candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    (work / "params.json").write_text(json.dumps({
        "skill_run": "edna-crosscheck", "input_mode": "genus-narrow", "realm": realm,
        "buffer_km": buffer_km, "genera": sorted(genera), "max_sp_per_genus": max_sp,
        "backbones": {"gbif": True, "worms": realm == "marine", "fishbase": True},
        # Propagate user_email from the upstream preflight so any downstream
        # consumer (subsequent genus-narrow runs, viz) reads the same value.
        "user_email": user_email,
    }, indent=2))
    n_genera = len(genera)
    print(f"genus-narrow: {n_genera} genera -> {len(out_rows)} candidate rows -> {out/'genus_candidates.csv'}")


if __name__ == "__main__":
    main()