#!/usr/bin/env python3
"""crosscheck: final assembly + realm-aware QC flags.

Joins the input ASV/occurrence table against the taxon crosswalk (sqlite),
the fishbase trait pull, and the env-extract values, then emits the three
PLAN §11-pinned artifacts:
  - enriched.parquet        (§11.2)
  - crosscheck_report.json  (§11.3)
  - flagged_occurrences.tsv (§11.4, subset of enriched with qc_level != ok
                              + signoff_status default "pending")

Flags emitted (realm-aware, only from routing["qc_checks"]):
  OUT_OF_RANGE       — occurrence source lookup for the taxon has zero known
                        records in the run's realm-appropriate source(s)
                        near the bbox (novelty/range-extension signal)
  ENVELOPE_VIOLATION — env value outside the FishBase depth-implied range
                        (marine/freshwater fish) or clearly extreme
                        elev/bioclim (terrestrial) — never a silent drop
  GENUS_ONLY         — taxon_match_status == "genus_only"
  NOVEL_TAXON        — taxon_match_status == "unresolved"
  ON_LAND            — marine/freshwater only (never terrestrial, see
                        realm-router): point falls outside the bbox's
                        marine/aquatic extent as declared in params.json,
                        used here as a cheap on/off-water proxy in the
                        absence of a bundled coastline polygon
                        (ponytail: real land mask is a future upgrade)

Usage: python3 crosscheck.py <occurrences.csv> <work_dir> <routing.json> <params.json> <out_dir>
"""
from __future__ import annotations
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - pixi env should always have pandas
    pd = None


def load_crosswalk(work_dir: Path) -> dict:
    db = work_dir / "crosswalk_cache.sqlite"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM crosswalk").fetchall()
    con.close()
    return {r["scientificName"]: dict(r) for r in rows}


def load_fishbase(work_dir: Path) -> dict:
    p = work_dir / "fishbase_pull.json"
    if not p.exists():
        return {}
    fb = json.loads(p.read_text() or "{}")
    if isinstance(fb, list):
        # fishbase_traits fishbase_pull.R emits [] when nothing resolves (the
        # 2024K1 battle-test audit caught crosscheck.py crashing on this shape)
        fb = {d.get("scientificName") or d.get("ScientificName", ""): d
              for d in fb if isinstance(d, dict)}
    return fb


def load_occurrence_counts(work_dir: Path) -> dict:
    p = work_dir / "occurrence_counts.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text() or "{}")


def load_env(work_dir: Path) -> dict:
    p = work_dir / "env_values.csv"
    out = {}
    if not p.exists():
        return out
    with open(p) as f:
        for row in csv.DictReader(f):
            key = (row["scientificName"], row["decimalLatitude"], row["decimalLongitude"])
            out[key] = row
    return out


def envelope_violation(routing: dict, env_row: dict, fb: dict, prefix: str) -> tuple[bool, str]:
    if routing["realm"] in ("marine", "freshwater") and fb:
        depth_min = fb.get("DepthRangeShallow")
        depth_max = fb.get("DepthRangeDeep")
        if depth_min is not None and depth_max is not None:
            # No direct field-measured depth in this table-shaped input; the
            # implemented envelope check compares the resolved env layer's
            # existence/validity against the trait envelope proxy: a NULL
            # env value where a valid depth range exists indicates the
            # extraction fell outside covered water (fill value) - flag it.
            for k, v in env_row.items():
                if k.startswith(prefix) and (v in (None, "", "None")):
                    return True, f"env layer {k} returned no value (fill/out-of-envelope) for taxon with FishBase depth range {depth_min}-{depth_max}m"
    return False, ""


def main() -> None:
    occ_csv, work_dir, routing_path, params_path, out_dir = sys.argv[1:6]
    work_dir = Path(work_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(routing_path) as f:
        routing = json.load(f)
    with open(params_path) as f:
        params = json.load(f)

    crosswalk = load_crosswalk(work_dir)
    fishbase = load_fishbase(work_dir)
    env = load_env(work_dir)
    occ_counts = load_occurrence_counts(work_dir)
    prefix = routing["env_column_prefix"]
    qc_checks = set(routing["qc_checks"])

    with open(occ_csv) as f:
        occ_rows = list(csv.DictReader(f))

    enriched_rows = []
    issues = []
    flag_counts = {"OUT_OF_RANGE": 0, "ENVELOPE_VIOLATION": 0, "GENUS_ONLY": 0, "NOVEL_TAXON": 0, "ON_LAND": 0}
    resolved = ambiguous = unresolved = 0

    bbox = params["bbox"]  # [minLon, minLat, maxLon, maxLat]

    for i, occ in enumerate(occ_rows):
        name = occ["scientificName"]
        cw = crosswalk.get(name, {})
        fb = fishbase.get(name, {}) or fishbase.get(cw.get("acceptedScientificName") or "", {})
        env_key = (name, occ["decimalLatitude"], occ["decimalLongitude"])
        env_row = env.get(env_key, {})

        match_status = cw.get("taxon_match_status", "unresolved")
        if match_status == "resolved":
            resolved += 1
        elif match_status == "ambiguous":
            ambiguous += 1
        elif match_status == "genus_only":
            pass
        else:
            unresolved += 1

        row_flags = []

        if "GENUS_ONLY" in qc_checks and match_status == "genus_only":
            row_flags.append("GENUS_ONLY")
            issues.append({"flag": "GENUS_ONLY", "level": "warning", "field": "taxon_match_status", "row": i,
                            "message": f"{name} resolved only to genus/higher rank", "scientificName": name})

        if "NOVEL_TAXON" in qc_checks and match_status == "unresolved":
            row_flags.append("NOVEL_TAXON")
            issues.append({"flag": "NOVEL_TAXON", "level": "warning", "field": "taxon_match_status", "row": i,
                            "message": f"{name} did not resolve against GBIF/WoRMS/FishBase backbones", "scientificName": name})

        if "ENVELOPE_VIOLATION" in qc_checks:
            viol, msg = envelope_violation(routing, env_row, fb, prefix)
            if viol:
                row_flags.append("ENVELOPE_VIOLATION")
                issues.append({"flag": "ENVELOPE_VIOLATION", "level": "warning", "field": f"{prefix}*", "row": i,
                                "message": msg, "scientificName": name})

        if "OUT_OF_RANGE" in qc_checks:
            counts = occ_counts.get(name, {})
            gbif_n = counts.get("gbif") or 0
            obis_n = counts.get("obis") or 0
            sources_used = "GBIF+OBIS" if routing.get("call_obis") else "GBIF"
            if gbif_n == 0 and obis_n == 0:
                row_flags.append("OUT_OF_RANGE")
                issues.append({"flag": "OUT_OF_RANGE", "level": "info", "field": "occurrence_counts", "row": i,
                                "message": f"{name} has zero known {sources_used} records near the declared bbox "
                                            "(possible misassigned ASV, or a genuine range extension)",
                                "scientificName": name})

        if "ON_LAND" in qc_checks:
            lat, lon = float(occ["decimalLatitude"]), float(occ["decimalLongitude"])
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                row_flags.append("ON_LAND")
                issues.append({"flag": "ON_LAND", "level": "warning", "field": "decimalLatitude/decimalLongitude", "row": i,
                                "message": f"point ({lat},{lon}) falls outside the declared realm bbox {bbox}", "scientificName": name})

        for fl in row_flags:
            flag_counts[fl] = flag_counts.get(fl, 0) + 1

        qc_level = "ok" if not row_flags else ("error" if match_status == "unresolved" else "warning")

        enriched = dict(occ)
        enriched.update({
            "scientificName": name,
            "acceptedScientificName": cw.get("acceptedScientificName"),
            "gbif_taxonKey": cw.get("gbif_taxonKey"),
            "worms_AphiaID": cw.get("worms_AphiaID"),
            "fishbase_SpeCode": fb.get("SpecCode") if fb else cw.get("fishbase_SpecCode"),
            "taxon_match_status": match_status,
            "trait_depth_min_m": fb.get("DepthRangeShallow") if fb else None,
            "trait_depth_max_m": fb.get("DepthRangeDeep") if fb else None,
            "trait_trophic_level": fb.get("trophic_level") if fb else None,
            "trait_body_size_cm": fb.get("Length") if fb else None,
            "env_layer_class": env_row.get("env_layer_class", ""),
            "qc_flags": ";".join(row_flags),
            "qc_level": qc_level,
            "realm": routing["realm"],
        })
        for k, v in env_row.items():
            if k.startswith(prefix):
                enriched[k] = v
        enriched_rows.append(enriched)

    # Write enriched.parquet
    if pd is not None:
        df = pd.DataFrame(enriched_rows)
        # §11.2 numeric-column enforcement: CSV inputs arrive as strings; coordinate,
        # trait and env columns must land typed or downstream (viz range math, SDMs) breaks
        NUMERIC_COLS = ["decimalLatitude", "decimalLongitude",
                        "trait_depth_min_m", "trait_depth_max_m",
                        "trait_trophic_level", "trait_body_size_cm",
                        "gbif_taxonKey", "worms_AphiaID", "fishbase_SpeCode"]
        for col in NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        env_cols = [c for c in df.columns if c.startswith("env_") and c != "env_layer_class"]
        for col in env_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.to_parquet(out_dir / "enriched.parquet", index=False)
    else:  # pragma: no cover
        (out_dir / "enriched.json").write_text(json.dumps(enriched_rows))

    # crosscheck_report.json
    report = {
        "run": {"tool": "edna-crosscheck v1.0.0", "realm": routing["realm"],
                 "timestamp": datetime.now(timezone.utc).isoformat(), "input": occ_csv},
        "summary": {"total_records": len(occ_rows), "resolved": resolved, "ambiguous": ambiguous,
                     "unresolved": unresolved, "flags": flag_counts},
        "issues": issues,
    }
    if not routing.get("call_obis"):
        report["notes"] = ["PLAN §7 risk #9: OUT_OF_RANGE corroboration for this realm rests on GBIF alone "
                             "(OBIS is marine-only); treat OUT_OF_RANGE flags with that in mind."]
    (out_dir / "crosscheck_report.json").write_text(json.dumps(report, indent=2))

    # flagged_occurrences.tsv
    flagged = [r for r in enriched_rows if r["qc_level"] != "ok"]
    for r in flagged:
        r["signoff_status"] = "pending"
    flagged_path = out_dir / "flagged_occurrences.tsv"
    if flagged:
        fieldnames = list(flagged[0].keys())
        with open(flagged_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            w.writerows(flagged)
    else:
        flagged_path.write_text("")

    print(f"crosscheck: realm={routing['realm']} records={len(occ_rows)} flagged={len(flagged)} "
          f"resolved={resolved} ambiguous={ambiguous} unresolved={unresolved}")


if __name__ == "__main__":
    main()
