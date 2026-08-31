#!/usr/bin/env python3
"""occurrence-publish — sub-skill 1: preflight (input validation + HARD GATE a).

Validates the PLAN §11.7 input contract:
  <run-dir>/enriched.parquet        (PLAN §11.2 columns)
  <run-dir>/flagged_occurrences.tsv (PLAN §11.4 — signoff_status gate)
  <run-dir>/params.json             (run manifest, PLAN §11.1)

HARD GATE (a): any flagged_occurrences.tsv row with signoff_status == "pending"
hard-blocks publish — exit 2 with a per-row report until every row is
approved/excluded.

Emits:  <work>/gate_report.json, <work>/publish_commands.sh (skeleton)
Exit:   0 = gates passed;  2 = blocked (gate a or contract violation)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

REQUIRED_ENRICHED = [
    "scientificName", "acceptedScientificName", "decimalLatitude", "decimalLongitude",
    "eventDate", "taxon_match_status", "qc_flags", "qc_level", "realm",
]
OPTIONAL_WARN = [
    "gbif_taxonKey", "worms_AphiaID", "fishbase_SpeCode", "dna_sequence",
    "asv_id", "reads", "total_reads", "associatedSequences",
]
ALLOWED_SIGNOFF = {"pending", "approved", "excluded"}
ALLOWED_REALM = {"marine", "freshwater", "terrestrial"}


def load_tsv(path: Path):
    import csv
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="crosscheck output dir")
    ap.add_argument("--work", default=".", help="this skill's run/work dir")
    args = ap.parse_args()
    run_dir, work = Path(args.run_dir), Path(args.work)
    work = work if work.name == "work" else work / "work"
    work.mkdir(parents=True, exist_ok=True)

    report = {"tool": "occurrence-publish preflight v1.0.0", "run_dir": str(run_dir),
              "checks": [], "gate_a": None, "gate_b": None, "gate_c": "upstream",
              "pending_rows": [], "flagged_summary": {}, "degraded": {}}
    ok = True

    # ---- manifest
    manifest_p = run_dir / "params.json"
    if not manifest_p.is_file():
        print(f"[preflight] FATAL: run manifest not found: {manifest_p}")
        return 2
    manifest = json.loads(manifest_p.read_text())
    realm = manifest.get("realm", "")
    if realm not in ALLOWED_REALM:
        print(f"[preflight] FATAL: manifest realm '{realm}' not in {sorted(ALLOWED_REALM)}")
        return 2
    report["realm"] = realm
    report["gate_b"] = "marine_only_refusal_if_nonmarine" if realm != "marine" else "obis_allowed"
    print(f"[preflight] manifest realm={realm!r} marker={manifest.get('marker')!r}")

    # ---- enriched.parquet
    parquet_p = run_dir / "enriched.parquet"
    if not parquet_p.is_file():
        print(f"[preflight] FATAL: enriched.parquet not found: {parquet_p}")
        return 2
    import pandas as pd
    df = pd.read_parquet(parquet_p)
    missing = [c for c in REQUIRED_ENRICHED if c not in df.columns]
    if missing:
        print(f"[preflight] FATAL: missing required column(s) (PLAN §11.2): {missing}")
        return 2
    # §11.2: rows lacking a 'realm' column value → fall back to manifest realm (SP-P3)
    if "realm" in df.columns and df["realm"].isna().any():
        n = int(df["realm"].isna().sum())
        df["realm"] = df["realm"].fillna(realm)
        report["degraded"]["realm_fallback_rows"] = n
        print(f"[preflight] NOTE: {n} parquet rows lacked realm; fell back to manifest realm")
    warn_missing = [c for c in OPTIONAL_WARN if c not in df.columns]
    if warn_missing:
        report["degraded"]["optional_columns_absent"] = warn_missing
        print(f"[preflight] NOTE (non-blocking): optional columns absent: {warn_missing}")
    report["enriched_rows"] = int(len(df))

    # ---- flagged_occurrences.tsv + HARD GATE (a)
    flagged_p = run_dir / "flagged_occurrences.tsv"
    if not flagged_p.is_file():
        print(f"[preflight] FATAL: flagged_occurrences.tsv not found: {flagged_p}")
        return 2
    flagged = load_tsv(flagged_p)
    bad_status = [r for r in flagged if r.get("signoff_status") not in ALLOWED_SIGNOFF]
    if bad_status:
        print(f"[preflight] FATAL: {len(bad_status)} flagged rows have invalid signoff_status "
              f"(allowed: {sorted(ALLOWED_SIGNOFF)})")
        return 2
    counts = {}
    for r in flagged:
        counts[r["signoff_status"]] = counts.get(r["signoff_status"], 0) + 1
    report["flagged_summary"] = counts
    report["flagged_rows_total"] = len(flagged)
    pending = [r for r in flagged if r["signoff_status"] == "pending"]

    if pending:
        report["gate_a"] = "BLOCKED"
        report["pending_rows"] = [
            {"row": i, "scientificName": r.get("scientificName", ""),
             "qc_flags": r.get("qc_flags", ""), "qc_level": r.get("qc_level", ""),
             "signoff_status": r.get("signoff_status")}
            for i, r in enumerate(pending)]
        (work / "gate_report.json").write_text(json.dumps(report, indent=2))
        print(f"[preflight] GATE-A: {len(pending)} pending flagged record(s) — publish ABORTED.")
        print("[preflight] Every row needs signoff_status approved/excluded (PLAN §11.4).")
        for p in report["pending_rows"][:20]:
            print(f"  row {p['row']}: {p['scientificName']} flags={p['qc_flags']} ({p['signoff_status']})")
        if len(report["pending_rows"]) > 20:
            print(f"  ... and {len(report['pending_rows']) - 20} more (see {work}/gate_report.json)")
        return 2

    report["gate_a"] = "passed"
    excluded = counts.get("excluded", 0)
    approved = counts.get("approved", 0)
    print(f"[preflight] GATE-A: passed — flagged rows: {approved} approved, {excluded} excluded, 0 pending")

    # ---- gate report + publish-commands skeleton
    (work / "gate_report.json").write_text(json.dumps(report, indent=2))
    cmds = work / "publish_commands.sh"
    if not cmds.exists():
        cmds.write_text(
            "#!/usr/bin/env bash\n"
            "# occurrence-publish v1.0.0 — READY-TO-RUN publish commands (user executes; NO live\n"
            "# publishing is performed by this skill in v1).\n"
            f"# run_dir: {run_dir}   realm: {realm}\n"
            "set -euo pipefail\n")
    print(f"[preflight] wrote {work}/gate_report.json — verdict GO for gbif-publish"
          + (" and obis-publish" if realm == "marine" else " (obis-publish will refuse: non-marine)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())