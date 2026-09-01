#!/usr/bin/env python3
"""Render the occurrence-crosscheck single-folder HTML report.

I/O contract
------------
Inputs (all CLI-supplied paths; nothing about a specific run is hardcoded):
  --params              params.json    -> realm, marker, buffer.km, input_extent (detection site lon/lat)
  --counts              occurrence_counts.json -> {scientificName: {gbif: int, obis: int}}
  --habitat             habitat_iucn.csv        -> per-taxon habitat flags + IUCN category
                          (candidate_of empty => detected species row; set => genus-candidate row)
  --species-images      species_images.csv      -> photo/license/attribution for detected species
  --candidate-images    candidate_images.csv     -> same, for genus candidates (candidate_display holds
                          the full authority-bearing name used to line up with genus_candidates.csv)
  --candidates          genus_candidates.csv     -> genus, candidate_species (w/ authority), rank,
                          n_records_in_buffer, sources, n_detection_sites, buffer_km
  --context             context_occurrences.csv  -> raw GBIF/OBIS occurrence points for detected species
  --candidates-context  candidates_context_occurrences.csv -> same, for genus candidates
  --species-maps        dir of "<Genus_species>__VERDICT.png"        (verdict cross-check source of truth)
  --candidate-panels    dir of "<Genus>__rank<N>_<slug>__PLAUSIBILITY.png" (plausibility cross-check source)
  --figures             dir of the fixed-name overview figures (01_occurrence_map.png etc.)
  --images-dir          dir holding the local_file paths referenced by species/candidate image CSVs
  --out                 output report directory; writes <out>/index.html (assets are referenced by
                         relative path from --out, never copied)

Verdict logic (must match viz v1.3.0 R pipeline exactly):
  NO_RECORD  if gbif + obis == 0
  CONCORDANT if nearest_km <= --near-km
  DISCORDANT otherwise
Nearest-record distance is the minimum haversine distance (km) from every context-occurrence point
for that taxon to the detection site (params.input_extent[0:2] = [lon, lat]).

Every computed verdict/plausibility is cross-checked against the species_maps / candidate_panels
filename suffix before rendering. A mismatch, an ambiguous multi-file match, or a missing map file
is a hard failure (exit 2) -- this script never renders a verdict it has not proven against the
existing map asset.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import jinja2

VERSION = "2.0.0"

VERDICTS = ("CONCORDANT", "DISCORDANT", "NO_RECORD")
PLAUSIBILITIES = ("SUPPORTED", "WEAK", "NO_RECORD")


def slugify(name: str) -> str:
    """Mirror viz's R `slug <- function(x) gsub("[^A-Za-z0-9._-]+", "_", x)` exactly --
    every filename this cross-checks against was produced by that function, so a run of any
    number of non [A-Za-z0-9._-] characters (spaces, "&", ",", parens, unicode) collapses to
    a single underscore, matching R's regex `+` quantifier."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())


def strip_authority(scientific_name: str) -> str:
    """Genus + species epithet only, authority (year/parens/capitalized surname) stripped."""
    parts = scientific_name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return scientific_name.strip()


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def circle_points(center_lon: float, center_lat: float, radius_km: float, n: int = 200):
    """n (lon, lat) points approximating a geodesic circle of radius_km around the center."""
    r_earth = 6371.0088
    d_ang = radius_km / r_earth
    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)
    pts = []
    for i in range(n + 1):
        bearing = 2 * math.pi * i / n
        lat2 = math.asin(
            math.sin(lat1) * math.cos(d_ang) + math.cos(lat1) * math.sin(d_ang) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(d_ang) * math.cos(lat1),
            math.cos(d_ang) - math.sin(lat1) * math.sin(lat2),
        )
        pts.append((math.degrees(lon2), math.degrees(lat2)))
    return pts


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def find_unique_map(directory: Path, prefix: str, allowed_suffixes: tuple[str, ...], label: str) -> tuple[str, Path]:
    """Find the single PNG in `directory` matching '<prefix>__<SUFFIX>.png'. Fail loudly otherwise."""
    matches = []
    for suffix in allowed_suffixes:
        candidate = directory / f"{prefix}__{suffix}.png"
        if candidate.exists():
            matches.append((suffix, candidate))
    if not matches:
        print(f"FATAL: no map file found for {label} (prefix {prefix!r}) in {directory}", file=sys.stderr)
        sys.exit(2)
    if len(matches) > 1:
        found = ", ".join(s for s, _ in matches)
        print(
            f"FATAL: ambiguous map files for {label} (prefix {prefix!r}) in {directory} "
            f"-- multiple verdict suffixes present: {found}. Refusing to guess.",
            file=sys.stderr,
        )
        sys.exit(2)
    return matches[0]


def relpath(out_dir: Path, target: Path) -> str:
    import os

    return os.path.relpath(target.resolve(), out_dir.resolve())


def resolve_image(images_dir: Path, local_file: str) -> Path | None:
    """Resolve a manifest local_file against --images-dir robustly.

    local_file is sometimes already relative to the manifest's PARENT (e.g.
    'images/Acanthopagrus_latus.jpg' with --images-dir .../species-images-poc/images),
    and sometimes a bare basename. Try the joins in order; first existing wins.
    """
    if not local_file:
        return None
    cands = [images_dir / local_file,
             images_dir.parent / local_file,
             images_dir / Path(local_file).name]
    for c in cands:
        if c.is_file():
            return c
    return None


def build_species(args, params, counts, habitat_rows, image_rows, context_rows, out_dir):
    det_lon, det_lat = params["input_extent"][0], params["input_extent"][1]
    near_km = args.near_km

    habitat_by_name = {r["scientificName"]: r for r in habitat_rows if not r.get("candidate_of")}
    images_by_name = {r["scientificName"]: r for r in image_rows}

    ctx_by_name: dict[str, list[dict]] = {}
    for row in context_rows:
        ctx_by_name.setdefault(row["scientificName"], []).append(row)

    names = sorted(counts.keys())
    if args.species_limit is not None:
        names = names[: args.species_limit]

    species = []
    verdict_hist = {"CONCORDANT": 0, "DISCORDANT": 0, "NO_RECORD": 0}
    iucn_hist: dict[str, int] = {}
    habitat_hist = {"marine": 0, "brackish": 0, "freshwater": 0, "terrestrial": 0}

    for name in names:
        c = counts[name]
        gbif_n, obis_n = int(c.get("gbif", 0)), int(c.get("obis", 0))
        total = gbif_n + obis_n
        # v2.5.1 merged-ring semantics (PLAN §11.13): world counts make NO_RECORD mean
        # "absent from GBIF/OBIS everywhere we looked"; beyond-ring = world − region
        gbif_w, obis_w = c.get("gbif_world"), c.get("obis_world")
        has_world = gbif_w is not None or obis_w is not None
        world_total = (int(gbif_w or 0)) + (int(obis_w or 0))
        gbif_out = max(0, int(gbif_w) - gbif_n) if gbif_w is not None else None
        obis_out = max(0, int(obis_w) - obis_n) if obis_w is not None else None

        pts = ctx_by_name.get(name, [])
        nearest_km = None
        for p in pts:
            d = haversine_km(det_lon, det_lat, float(p["decimalLongitude"]), float(p["decimalLatitude"]))
            if nearest_km is None or d < nearest_km:
                nearest_km = d

        if has_world and world_total == 0:
            verdict = "NO_RECORD"          # absent from GBIF/OBIS globally
        elif nearest_km is not None and nearest_km <= near_km:
            verdict = "CONCORDANT"
        elif has_world:
            verdict = "DISCORDANT"          # occurs somewhere, but not within the ring
        elif total == 0 and not pts:
            verdict = "NO_RECORD"          # legacy manifests (no world counts)
        else:
            verdict = "DISCORDANT"

        slug = slugify(name)
        found_suffix, map_path = find_unique_map(args.species_maps, slug, VERDICTS, name)
        if found_suffix != verdict:
            print(
                f"FATAL: verdict mismatch for {name!r}: computed={verdict} filename={found_suffix} "
                f"({map_path.name})",
                file=sys.stderr,
            )
            sys.exit(2)

        verdict_hist[verdict] += 1

        hab = habitat_by_name.get(name, {})
        iucn_cat = hab.get("iucn_category", "") or "Not Evaluated"
        iucn_hist[iucn_cat] = iucn_hist.get(iucn_cat, 0) + 1
        for flag in ("marine", "brackish", "freshwater", "terrestrial"):
            if hab.get(flag) == "1":
                habitat_hist[flag] += 1

        img = images_by_name.get(name)
        image_entry = None
        if img and img.get("local_file") and img.get("flag") != "flag-no-image":
            local = resolve_image(args.images_dir, img["local_file"])
            if local is not None:
                image_entry = {
                    "path": relpath(out_dir, local),
                "license": img.get("license", ""),
                "creator": img.get("creator", "") or img.get("rightsHolder", ""),
                "source": img.get("source", ""),
                "occurrence_url": img.get("occurrence_url", ""),
                "placeholder": False,
            }
        else:
            image_entry = {
                "path": None,
                "flag": (img.get("flag") if img else "") or "no-image",
                "placeholder": True,
            }

        species.append(
            {
                "name": name,
                "name_short": strip_authority(name),
                "verdict": verdict,
                "gbif": gbif_n,
                "obis": obis_n,
                "total": total,
                "nearest_km": round(nearest_km, 1) if nearest_km is not None else None,
                "gbif_out": gbif_out,
                "obis_out": obis_out,
                "map_path": relpath(out_dir, map_path),
                "habitat": hab.get("habitat", ""),
                "flags": {
                    "marine": hab.get("marine") == "1",
                    "brackish": hab.get("brackish") == "1",
                    "freshwater": hab.get("freshwater") == "1",
                    "terrestrial": hab.get("terrestrial") == "1",
                },
                "iucn_code": hab.get("iucn_code", "") or "NE",
                "iucn_category": iucn_cat,
                "worms_status": hab.get("worms_status", ""),
                "habitat_flag": hab.get("flag", ""),
                "image": image_entry,
            }
        )

    return species, verdict_hist, iucn_hist, habitat_hist


def build_candidates(args, habitat_rows, image_rows, candidate_rows, context_rows):
    """Stage 1: attach raw context points to each candidate row (no verdict math yet).

    context_rows = candidates_context + detected-species backdrop MERGED, mirroring
    plot_genus_candidates.R (rbind of --overlay + --candidates-context then binomial-key
    join). The candidates-only fetch is GBIF-only and 100-row-capped, so the detected
    backdrop contributes nearer OBIS records for candidates that are also detected taxa;
    the binomial-key join makes the merge a no-op for all other candidates.
    """
    habitat_by_display = {r["scientificName"]: r for r in habitat_rows if r.get("candidate_of")}
    images_by_display = {r.get("candidate_display", r["scientificName"]): r for r in image_rows}

    ctx_by_short: dict[str, list[dict]] = {}
    for row in context_rows:
        ctx_by_short.setdefault(row["scientificName"], []).append(row)

    rows = candidate_rows
    # Mirror plot_genus_candidates.R --max-candidates (default 3): only the top-N
    # rank-sorted candidates per genus get panels rendered, so only they are reportable.
    max_c = getattr(args, "max_candidates", 3) or 3
    by_genus: dict[str, list[dict]] = {}
    for r in rows:
        by_genus.setdefault(r["genus"], []).append(r)
    rows = []
    for g in sorted(by_genus):
        per = sorted(by_genus[g], key=lambda r: int(r.get("rank", 0) or 0))
        rows.extend(per[:max_c])
    if args.candidates_limit is not None:
        rows = rows[: args.candidates_limit]

    candidates = []

    for row in rows:
        genus = row["genus"]
        display_name = row["candidate_species"]
        rank = row["rank"]
        short_name = strip_authority(display_name)

        pts = ctx_by_short.get(short_name, [])
        n_records = int(row.get("n_records_in_buffer", 0) or 0)
        candidates.append(
            {
                "_row": row,
                "genus": genus,
                "display_name": display_name,
                "short_name": short_name,
                "rank": rank,
                "n_records": n_records,
                "sources": row.get("sources", ""),
                "n_sites": row.get("n_detection_sites", ""),
                "buffer_km": row.get("buffer_km", ""),
                "ctx_points": pts,
            }
        )

    return candidates, habitat_by_display, images_by_display


def finish_candidates(args, params, candidates, habitat_by_display, images_by_display, out_dir):
    det_lon, det_lat = params["input_extent"][0], params["input_extent"][1]
    near_km = args.near_km
    plausibility_hist = {"SUPPORTED": 0, "WEAK": 0, "NO_RECORD": 0}
    out = []

    for cand in candidates:
        row = cand["_row"]
        pts = cand["ctx_points"]
        n_records = cand["n_records"]

        nearest_km = None
        for p in pts:
            d = haversine_km(det_lon, det_lat, float(p["decimalLongitude"]), float(p["decimalLatitude"]))
            if nearest_km is None or d < nearest_km:
                nearest_km = d

        if n_records == 0:
            plausibility = "NO_RECORD"
        elif nearest_km is not None and nearest_km <= near_km:
            plausibility = "SUPPORTED"
        else:
            plausibility = "WEAK"

        genus_slug = slugify(cand["genus"])
        name_slug = slugify(cand["display_name"])
        prefix = f"{genus_slug}__rank{cand['rank']}_{name_slug}"
        found_suffix, panel_path = find_unique_map(
            args.candidate_panels, prefix, PLAUSIBILITIES, cand["display_name"]
        )
        if found_suffix != plausibility:
            print(
                f"FATAL: plausibility mismatch for {cand['display_name']!r}: "
                f"computed={plausibility} filename={found_suffix} ({panel_path.name})",
                file=sys.stderr,
            )
            sys.exit(2)

        plausibility_hist[plausibility] += 1

        hab = habitat_by_display.get(cand["display_name"], {})
        img = images_by_display.get(cand["display_name"])
        if img and img.get("local_file") and img.get("flag") != "flag-no-image":
            local = resolve_image(args.images_dir, img["local_file"])
            image_entry = {
                "path": relpath(out_dir, local) if local is not None else None,
                "license": img.get("license", ""),
                "creator": img.get("creator", "") or img.get("rightsHolder", ""),
                "source": img.get("source", ""),
                "occurrence_url": img.get("occurrence_url", ""),
                "placeholder": False,
            }
        else:
            image_entry = {
                "path": None,
                "flag": (img.get("flag") if img else "") or "no-image",
                "placeholder": True,
            }

        out.append(
            {
                "genus": cand["genus"],
                "display_name": cand["display_name"],
                "short_name": cand["short_name"],
                "rank": cand["rank"],
                "n_records": n_records,
                "sources": cand["sources"],
                "n_sites": cand["n_sites"],
                "buffer_km": cand["buffer_km"],
                "nearest_km": round(nearest_km, 1) if nearest_km is not None else None,
                "plausibility": plausibility,
                "panel_path": relpath(out_dir, panel_path),
                "habitat": hab.get("habitat", ""),
                "iucn_code": hab.get("iucn_code", "") or "NE",
                "iucn_category": hab.get("iucn_category", "") or "Not Evaluated",
                "image": image_entry,
            }
        )

    return out, plausibility_hist


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--params", required=True, type=Path)
    ap.add_argument("--counts", required=True, type=Path)
    ap.add_argument("--habitat", required=True, type=Path)
    ap.add_argument("--species-images", required=True, type=Path)
    ap.add_argument("--candidate-images", required=True, type=Path)
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--context", required=True, type=Path)
    ap.add_argument("--candidates-context", required=True, type=Path)
    ap.add_argument("--species-maps", required=True, type=Path)
    ap.add_argument("--candidate-panels", required=True, type=Path)
    ap.add_argument("--figures", required=True, type=Path)
    ap.add_argument("--images-dir", required=True, type=Path)
    ap.add_argument("--max-candidates", type=int, default=3,
                    help="top-N candidates per genus rendered as panels (must match viz run; default 3)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--near-km", type=float, default=150.0)
    ap.add_argument("--species-limit", type=int, default=None)
    ap.add_argument("--candidates-limit", type=int, default=None)
    ap.add_argument("--version", action="version", version=f"build_report_html.py {VERSION}")
    args = ap.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    params = json.loads(args.params.read_text(encoding="utf-8"))
    counts = json.loads(args.counts.read_text(encoding="utf-8"))
    habitat_rows = read_csv(args.habitat)
    species_image_rows = read_csv(args.species_images)
    candidate_image_rows = read_csv(args.candidate_images)
    candidate_rows = read_csv(args.candidates)
    context_rows = read_csv(args.context)
    candidates_context_rows = read_csv(args.candidates_context)

    species, verdict_hist, iucn_hist, habitat_hist = build_species(
        args, params, counts, habitat_rows, species_image_rows, context_rows, out_dir
    )

    cand_stage1, habitat_by_display, images_by_display = build_candidates(
        args, habitat_rows, candidate_image_rows, candidate_rows,
        candidates_context_rows + context_rows,
    )
    candidates, plausibility_hist = finish_candidates(
        args, params, cand_stage1, habitat_by_display, images_by_display, out_dir
    )

    det_lon, det_lat = params["input_extent"][0], params["input_extent"][1]
    buffer_km = params.get("buffer", {}).get("km")
    # ring_km is the *displayed* concordance radius (defaults to the --near-km threshold used
    # for the CONCORDANT/DISCORDANT call) and may differ from buffer_km, the full data-fetch
    # radius -- a future params.json may carry an explicit "ring_km" override.
    ring_km = params.get("ring_km", args.near_km)

    ctx_points = []
    counted_names = {s["name"] for s in species}
    for row in context_rows:
        if row["scientificName"] not in counted_names:
            continue
        d = haversine_km(det_lon, det_lat, float(row["decimalLongitude"]), float(row["decimalLatitude"]))
        ctx_points.append(
            {
                "name": row["scientificName"],
                "lat": float(row["decimalLatitude"]),
                "lon": float(row["decimalLongitude"]),
                "src": row["source"],
                "ring": "in" if d <= ring_km else "out",
            }
        )

    ring_points = []
    if ring_km:
        ring_points = [{"lon": lo, "lat": la} for lo, la in circle_points(det_lon, det_lat, float(ring_km))]

    figures = {
        p.stem: relpath(out_dir, p) for p in sorted(args.figures.glob("*.png"))
    }

    report_data = {
        "meta": {
            "realm": params.get("realm", ""),
            "marker": params.get("marker", ""),
            "buffer_km": buffer_km,
            "ring_km": ring_km,
            "near_km": args.near_km,
            "run": args.params.parent.name,
            "params_path": str(args.params),
            "generator_version": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "detection_site": {"lon": det_lon, "lat": det_lat},
            "bbox": params.get("bbox"),
        },
        "species": species,
        "candidates": candidates,
        "counts": {
            "species_verdicts": verdict_hist,
            "candidate_plausibility": plausibility_hist,
            "iucn_hist": iucn_hist,
            "habitat_hist": habitat_hist,
        },
        "ctx_points": ctx_points,
        "ring_points": ring_points,
        "figures": figures,
    }

    template_dir = Path(__file__).resolve().parent.parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        undefined=jinja2.StrictUndefined,
        autoescape=jinja2.select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")

    # Vendor plotly.min.js into the report folder so the folder is self-contained and
    # portable (a relative path back into the skill tree would break once the report
    # folder is copied elsewhere for review).
    vendor_dir = out_dir / "vendor"
    plotly_src_file = Path(__file__).resolve().parent.parent / "vendor" / "plotly.min.js"
    if not plotly_src_file.is_file():
        raise SystemExit(f"FATAL: vendored plotly.min.js missing: {plotly_src_file}")
    vendor_dir.mkdir(parents=True, exist_ok=True)
    plotly_dst = vendor_dir / "plotly.min.js"
    if not plotly_dst.is_file() or plotly_dst.stat().st_size != plotly_src_file.stat().st_size:
        shutil.copyfile(plotly_src_file, plotly_dst)
    plotly_rel = "vendor/plotly.min.js"

    # ensure_ascii=False keeps names/attribution readable in the source; guard against a "</script>"
    # substring in any CSV-derived field (license text, attribution) prematurely closing the tag.
    data_json = json.dumps(report_data, ensure_ascii=False).replace("</", "<\\/")

    html = template.render(
        data_json=data_json,
        meta=report_data["meta"],
        plotly_src=plotly_rel,
        n_species=len(species),
        n_candidates=len(candidates),
    )

    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")

    assert out_file.exists() and out_file.stat().st_size > 0, "report write failed"

    print(
        f"report html: {len(species)} species, {len(candidates)} candidates, "
        f"{len(ctx_points)} ctx points -> {out_file}"
    )


if __name__ == "__main__":
    main()
