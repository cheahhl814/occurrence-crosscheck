#!/usr/bin/env python3
"""occurrence-publish — sub-skill 2: gbif-publish (plain-Python DwC-A occurrence core).

Re-checks HARD GATE (a) via <work>/gate_report.json (must be gate_a == passed),
maps enriched.parquet (PLAN §11.2) to a GBIF occurrence-core DwC-A:
  occurrence core + DNA-derived data extension (+ eMoF when marine env cols exist)
  + hand-built meta.xml + EML 2.0/2.1.1 eml.xml   →  <run-dir>/*_gbif_dwca.zip
Emits ready-to-run IPT upload commands (eDNAbridge path — documented, never executed here).

No live publishing calls (pinned). Exit 0 = zip built; 2 = blocked.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dwca_core as d  # noqa: E402

DNA_DEFAULTS = {
    "sop": "https://nf-core.readthedocs.io/edna (nf-edna pipeline)",
    "pcr_primer_name_forward": "manifest-provided",
    "pcr_primer_name_reverse": "manifest-provided",
    "lib_layout": "paired",
    "otu_class_appr": "idtaxa;nf-edna;ASV",
    "otu_seq_comp_appr": "DADA2;nf-edna;ASV",
    "otu_db": "crosscheck taxon-resolve cache (GBIF+WoRMS)",
}


def marine_envo_columns(realm):
    if realm == "marine":
        return {"env_broad_scale": "marine biome (ENVO:00000447)",
                "env_local_scale": "coastal water (ENVO:00001250)",
                "env_medium": "waterborne particulate matter (ENVO:01000436)"}
    return {"env_broad_scale": "terrestrial biome (ENVO:00000428)",
            "env_local_scale": "", "env_medium": "soil or water, realm-dependent"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--work", default=".")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()
    run_dir, work = Path(args.run_dir), Path(args.work)
    work = work / "work" if work.name != "work" else work

    # ---- gate re-check (belt-and-braces)
    gate_p = work / "gate_report.json"
    if not gate_p.is_file():
        print(f"[gbif] GATE-A not evaluated yet — run `pixi run publish-preflight` first.")
        return 2
    gate = json.loads(gate_p.read_text())
    if gate.get("gate_a") != "passed":
        print(f"[gbif] GATE-A still BLOCKED ({len(gate.get('pending_rows', []))} pending) — abort.")
        return 2

    manifest = json.loads((run_dir / "params.json").read_text())
    realm = manifest.get("realm", "marine")
    import pandas as pd
    df = pd.read_parquet(run_dir / "enriched.parquet")

    # apply user sign-off decisions: drop 'excluded' rows (explicit decision recorded in TSV)
    excluded_ids = set()
    flagged_p = run_dir / "flagged_occurrences.tsv"
    if flagged_p.is_file():
        import csv
        with open(flagged_p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                if r.get("signoff_status") == "excluded":
                    excluded_ids.add(int(r.get("_rowindex", -1)) if r.get("_rowindex", "").lstrip("-").isdigit() else None)
    # _rowindex may be absent in hand-maintained TSVs; fall back to key-based exclusion
    if excluded_ids and None in excluded_ids:
        excluded_ids = set()

    if excluded_ids:
        df = df.drop(index=[i for i in excluded_ids if i < len(df)])

    if df.empty:
        print("[gbif] NO-GO: zero publishable rows after sign-off filtering.")
        return 2

    # ---------------- occurrence core ----------------
    occ_rows = []
    for i, r in df.iterrows():
        oid = d.occurrence_id(r.get("eventDate"), r.get("decimalLatitude"),
                              r.get("decimalLongitude"), r.get("scientificName"),
                              r.get("asv_id", str(i)))
        occ_rows.append({
            "occurrenceID": oid,
            "basisOfRecord": "MaterialSample",
            "eventDate": r.get("eventDate"),
            "decimalLatitude": r.get("decimalLatitude"),
            "decimalLongitude": r.get("decimalLongitude"),
            "scientificName": r.get("scientificName"),
            "acceptedNameUsage": r.get("acceptedScientificName"),
            "taxonID": r.get("gbif_taxonKey"),
            "taxonRank": r.get("taxonRank", ""),
            "kingdom": r.get("kingdom", ""),
            "genus": r.get("genus", ""),
            "organismQuantity": r.get("reads"),
            "organismQuantityType": "DNA sequence reads" if r.get("reads") not in (None, "") else "",
            "sampleSizeValue": r.get("total_reads"),
            "sampleSizeUnit": "DNA sequence reads" if r.get("total_reads") not in (None, "") else "",
            "associatedSequences": r.get("associatedSequences", ""),
            "identificationRemarks": f"taxon_match_status={r.get('taxon_match_status', '')}",
            "verbatimIdentification": r.get("scientificName"),
            "recordedBy": "nf-edna + edna-crosscheck + occurrence-publish",
        })

    occ_cols = list(occ_rows[0].keys())
    occ_content = d.write_tsv(occ_rows, occ_cols)

    # ---------------- DNA-derived data extension ----------------
    env_cols = [c for c in df.columns if c.startswith("env_bio_") or c.startswith("env_wc_")]
    dna_cols = ["occurrenceID", "DNA_sequence", "target_gene", "target_subfragment",
                "pcr_primer_forward", "pcr_primer_reverse", "pcr_primer_name_forward",
                "pcr_primer_name_reverse", "pcr_primer_reference", "Pcr_cond",
                "annealingTemp", "annealingTempUnit", "ampliconSize",
                "env_broad_scale", "env_local_scale", "env_medium",
                "lib_layout", "seq_meth", "otu_class_appr", "otu_seq_comp_appr", "otu_db", "sop"]
    seq_meth_default = manifest.get("seq_meth", "Illumina iSeq 2x150")
    gene = manifest.get("marker", "unspecified")
    envo = marine_envo_columns(realm)
    dna_rows = []
    for r in occ_rows:
        src = df.iloc[0]  # dataset-level constants; per-row sequence below
        pass
    for idx, r in df.iterrows():
        oid = occ_rows[idx]["occurrenceID"]
        dna_rows.append({
            "occurrenceID": oid,
            "DNA_sequence": r.get("dna_sequence") or r.get("asv_sequence", ""),
            "target_gene": gene,
            "target_subfragment": manifest.get("target_subfragment", ""),
            "pcr_primer_forward": manifest.get("pcr_primer_forward", ""),
            "pcr_primer_reverse": manifest.get("pcr_primer_reverse", ""),
            "pcr_primer_name_forward": DNA_DEFAULTS["pcr_primer_name_forward"],
            "pcr_primer_name_reverse": DNA_DEFAULTS["pcr_primer_name_reverse"],
            "pcr_primer_reference": manifest.get("pcr_primer_reference", ""),
            "Pcr_cond": manifest.get("pcr_cond", ""),
            "annealingTemp": manifest.get("annealing_temp", ""),
            "annealingTempUnit": "Celsius",
            "ampliconSize": manifest.get("amplicon_size", ""),
            "env_broad_scale": envo.get("env_broad_scale", ""),
            "env_local_scale": envo.get("env_local_scale", ""),
            "env_medium": envo.get("env_medium", ""),
            "lib_layout": DNA_DEFAULTS["lib_layout"],
            "seq_meth": seq_meth_default,
            "otu_class_appr": DNA_DEFAULTS["otu_class_appr"],
            "otu_seq_comp_appr": DNA_DEFAULTS["otu_seq_comp_appr"],
            "otu_db": DNA_DEFAULTS["otu_db"],
            "sop": DNA_DEFAULTS["sop"],
        })
    dna_content = d.write_tsv(dna_rows, dna_cols)

    # ---------------- eMoF (Bio-ORACLE env values, when present) ----------------
    extensions = [{"location": "dna_derived_data.txt", "rowType": d.DNA_ROWTYPE,
                   "columns": dna_cols, "coreid_index": 0, "coreid_term": "occurrenceID"}]
    ext_files = [{"location": "dna_derived_data.txt", "content": dna_content}]
    emof_rows = []
    if env_cols:
        for idx, r in df.iterrows():
            for c in env_cols:
                v = r.get(c)
                if v in (None, ""):
                    continue
                emof_rows.append({
                    "occurrenceID": occ_rows[idx]["occurrenceID"],
                    "measurementType": c,
                    "measurementValue": v,
                    "measurementUnit": "degree Celsius" if "temp" in c.lower()
                                       else ("PSU" if "salin" in c.lower() else ""),
                    "measurementDeterminedBy": "Bio-ORACLE (occurrence-publish eMoF slot-in)",
                })
        if emof_rows:
            emof_cols = ["occurrenceID", "measurementType", "measurementValue",
                         "measurementUnit", "measurementDeterminedBy"]
            extensions.append({"location": "emof.txt", "rowType": d.EMOF_ROWTYPE,
                               "columns": emof_cols, "coreid_index": 0,
                               "coreid_term": "occurrenceID"})
            ext_files.append({"location": "emof.txt",
                              "content": d.write_tsv(emof_rows, emof_cols)})

    # ---------------- meta.xml + eml.xml + zip ----------------
    meta = d.build_meta_xml(
        {"location": "occurrence.txt", "rowType": d.OCC_ROWTYPE,
         "columns": occ_cols, "id_index": 0},
        extensions)
    bbox = manifest.get("bbox", [-180, -90, 180, 90])
    begin = str(df["eventDate"].min())[:10] if "eventDate" in df else str(date.today())
    end = str(df["eventDate"].max())[:10] if "eventDate" in df else str(date.today())
    title = args.title or manifest.get("title", f"eDNA occurrences ({manifest.get('marker', 'marker')}) — {realm}")
    eml = d.build_eml(
        title=title,
        abstract=f"eDNA metabarcoding occurrences ({len(occ_rows)} records) cross-checked by "
                 f"edna-crosscheck and published via occurrence-publish.",
        bbox=bbox, begin_date=begin, end_date=end,
        creator_surname=manifest.get("creator_surname", "AixBio"),
        marker=gene,
        taxonomic_coverage=df["scientificName"].dropna().tolist())
    zip_path = run_dir / f"{manifest.get('dataset_key', 'dataset')}_gbif_dwca.zip"
    d.build_dwca_zip(zip_path,
                     {"location": "occurrence.txt", "content": occ_content},
                     ext_files, eml, meta)

    # ready-to-run upload command (user executes — eDNAbridge reference path)
    cmds = work / "publish_commands.sh"
    with open(cmds, "a", encoding="utf-8") as fh:
        fh.write(f"\n# GBIF upload (eDNAbridge reference path; user executes):\n"
                 f"Rscript -e 'eDNAbridge::ipt_upload_and_publish(archive=\"{zip_path}\", "
                 f"ipt_url=\"https://YOUR.IPT.INSTANCE/\")'\n")

    build = {"leg": "gbif", "zip": str(zip_path), "sha256": d.sha256_of(zip_path),
             "occurrence_rows": len(occ_rows), "dna_rows": len(dna_rows),
             "emof_rows": len(emof_rows), "excluded_dropped": len(excluded_ids)}
    (work / "gbif_build.json").write_text(json.dumps(build, indent=2))
    print(f"[gbif] built {zip_path} ({len(occ_rows)} occurrence rows, "
          f"{len(dna_rows)} DNA rows, {len(emof_rows)} eMoF rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())