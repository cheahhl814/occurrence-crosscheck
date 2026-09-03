#!/usr/bin/env python3
"""occurrence-publish — sub-skill 3: obis-publish (OBIS Event-Core DwC-A; MARINE ONLY).

HARD GATE (b): refuses with a clear message when manifest realm != "marine"
(OBIS does not accept terrestrial/freshwater datasets).

HARD GATE (c): hard-rejects any record without a WoRMS-valid scientificNameID
(urn:lsid:marinespecies.org:taxname:N). Produces NO zip while any row fails.

Structure per http://manual.obis.org/dna_data.html (docs-corpus/obis-dna-data/):
  Event core: CRU::<dataset> :: ST<station> :: SMP<n> :: SEQ<k>  (parent/child)
  + Occurrence extension (eventID link) + DNA-derived data extension
  + eMoF/OBIS-ENV-DATA (Bio-ORACLE env_* values slot in; omitted if absent)

Exit 0 = zip built; 2 = gate refusal / hard reject; 3 = gate (c) rejections.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dwca_core as d  # noqa: E402

WORMS_LSID_RE = re.compile(r"^urn:lsid:marinespecies\.org:taxname:\d+$")
BIOTA_SEDIS_LSID = "urn:lsid:marinespecies.org:taxname:12"
BIOTA_SEDIS_NAME = "Biota incertae sedis"


def is_missing(v):
    if v is None:
        return True
    try:
        return bool(v != v)  # NaN
    except (TypeError, ValueError):
        return True  # pd.NA / other ambiguous missing markers


def science_name_id(aphia):
    try:
        if aphia is None or (aphia != aphia):  # None or NaN
            return ""
    except TypeError:
        return ""  # pd.NA is ambiguous in boolean context -> treated as missing
    s = str(aphia).strip()
    if s in ("", "None", "<NA>", "NA", "nan"):
        return ""
    try:
        return f"urn:lsid:marinespecies.org:taxname:{int(float(s))}"
    except (ValueError, TypeError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--work", default=".")
    ap.add_argument("--allow-incertae-sedis", action="store_true",
                    help="map rows with a taxon_match_status but no AphiaID ... (still requires "
                         "an LSID; unresolved rows use Biota incertae sedis LSID 12 per manual)")
    args = ap.parse_args()
    run_dir, work = Path(args.run_dir), Path(args.work)
    work = work / "work" if work.name != "work" else work

    manifest = json.loads((run_dir / "params.json").read_text())
    realm = manifest.get("realm", "")

    # ---------------- HARD GATE (b): marine-only ----------------
    if realm != "marine":
        print(f"[obis] GATE-B: OBIS refuses non-marine datasets (realm={realm!r}).\n"
              f"       OBIS does not accept terrestrial or freshwater datasets — publish to "
              f"GBIF only (pixi run gbif-publish), or re-declare realm=marine at crosscheck "
              f"preflight if this dataset really is marine.")
        return 2

    # gate a belt-and-braces
    gate_p = work / "gate_report.json"
    if gate_p.is_file():
        gate = json.loads(gate_p.read_text())
        if gate.get("gate_a") != "passed":
            print(f"[obis] GATE-A still BLOCKED ({len(gate.get('pending_rows', []))} pending) — abort.")
            return 2

    import pandas as pd
    df = pd.read_parquet(run_dir / "enriched.parquet")
    if df.empty:
        print("[obis] NO-GO: zero rows.")
        return 2

    # ---------------- HARD GATE (c): WoRMS LSID ----------------
    rejections = []
    names_to_lsids = {}
    station_ids, sample_ids, seq_ids = [], [], []
    ds_key = manifest.get("dataset_key", "eDNA")

    for i, r in df.iterrows():
        lsid = science_name_id(r.get("worms_AphiaID"))
        if lsid == "" and args.allow_incertae_sedis:
            lsid = BIOTA_SEDIS_LSID
            names_to_lsids[(r.get("scientificName"), i)] = (lsid, BIOTA_SEDIS_NAME)
        if not WORMS_LSID_RE.match(lsid):
            rejections.append({
                "row": int(i), "scientificName": r.get("scientificName", ""),
                "worms_AphiaID": None if is_missing(r.get("worms_AphiaID"))
                                 else str(r.get("worms_AphiaID")),
                "scientificNameID": lsid,
                "reason": "missing WoRMS AphiaID — scientificNameID is not a WoRMS-valid LSID "
                          "(urn:lsid:marinespecies.org:taxname:N)",
                "remediation": "backfill worms_AphiaID via crosscheck taxon-resolve, or "
                               f"(unassigned taxa only) use {BIOTA_SEDIS_NAME} LSID "
                               f"{BIOTA_SEDIS_LSID} with verbatimIdentification",
            })
        else:
            names_to_lsids[(r.get("scientificName"), i)] = (lsid, r.get("acceptedScientificName"))

    if rejections:
        rej_p = work / "obis_rejections.json"
        rej_p.write_text(json.dumps({"gate": "c", "refused_records": len(rejections),
                                     "rows": rejections}, indent=2))
        print(f"[obis] GATE-C: {len(rejections)} record(s) without a WoRMS-valid "
              f"scientificNameID — HARD REJECTED, no archive produced.")
        for rj in rejections[:20]:
            print(f"  row {rj['row']}: {rj['scientificName']} ({rj['reason']})")
        print(f"  full list: {rej_p}")
        print(f"  remediation: backfill crosswalk (taxon-resolve) or map unassigned taxa to "
              f"{BIOTA_SEDIS_NAME} LSID {BIOTA_SEDIS_LSID}; then re-run.")
        return 3

    # ---------------- Event core hierarchy ----------------
    stations = {}
    for i, r in df.iterrows():
        st_key = f"ST{int(i) + 1:03d}"
        stations[st_key] = r
    event_rows = []
    event_rows.append({
        "eventID": f"CRU::{ds_key}", "parentEventID": "",
        "type": "survey/cruise",
        "eventDate": str(df["eventDate"].min())[:10],
        "samplingProtocol": f"eDNA cruise {ds_key}",
        "decimalLatitude": "", "decimalLongitude": "",
        "minimumDepthInMeters": "", "maximumDepthInMeters": "",
        "sampleSizeValue": "", "sampleSizeUnit": "",
    })
    seq_meta = []
    for st_key, r in sorted(stations.items()):
        st_id = f"CRU::{ds_key}::{st_key}"
        event_rows.append({
            "eventID": st_id, "parentEventID": f"CRU::{ds_key}",
            "type": "station",
            "eventDate": str(r.get("eventDate"))[:10],
            "samplingProtocol": "water filtration (eDNA)",
            "decimalLatitude": r.get("decimalLatitude"),
            "decimalLongitude": r.get("decimalLongitude"),
            "minimumDepthInMeters": r.get("minimumDepthInMeters", "") or "",
            "maximumDepthInMeters": r.get("maximumDepthInMeters", "") or "",
            "sampleSizeValue": r.get("filter_volume_l", "") or "",
            "sampleSizeUnit": "litres filtered" if r.get("filter_volume_l") not in (None, "") else "",
        })
        smp_id = st_id + "::SMP1"
        event_rows.append({
            "eventID": smp_id, "parentEventID": st_id,
            "type": "sample",
            "eventDate": str(r.get("eventDate"))[:10],
            "samplingProtocol": "filter sample",
            "decimalLatitude": "", "decimalLongitude": "",
            "minimumDepthInMeters": "", "maximumDepthInMeters": "",
            "sampleSizeValue": "", "sampleSizeUnit": "",
        })
        seq_id = smp_id + "::SEQ1"
        event_rows.append({
            "eventID": seq_id, "parentEventID": smp_id,
            "type": "sequencing event",
            "eventDate": str(r.get("eventDate"))[:10],
            "samplingProtocol": f"{manifest.get('marker', 'marker')} metabarcoding "
                                f"({seq_meth_of(manifest)})",
            "decimalLatitude": "", "decimalLongitude": "",
            "minimumDepthInMeters": "", "maximumDepthInMeters": "",
            "sampleSizeValue": r.get("total_reads", "") or "",
            "sampleSizeUnit": "DNA sequence reads" if r.get("total_reads") not in (None, "") else "",
        })
        seq_ids.append(seq_id)
        station_ids.append(st_id)
        sample_ids.append(smp_id)

    event_cols = ["eventID", "parentEventID", "type", "eventDate", "samplingProtocol",
                  "decimalLatitude", "decimalLongitude", "minimumDepthInMeters",
                  "maximumDepthInMeters", "sampleSizeValue", "sampleSizeUnit"]
    event_content = d.write_tsv(event_rows, event_cols)

    # ---------------- Occurrence extension (eventID link) ----------------
    occ_rows = []
    for i, r in df.iterrows():
        lsid = names_to_lsids[(r.get("scientificName"), i)][0]
        oid = d.occurrence_id(r.get("eventDate"), r.get("decimalLatitude"),
                              r.get("decimalLongitude"), r.get("scientificName"),
                              r.get("asv_id", str(i)))
        occ_rows.append({
            "eventID": seq_ids[i],
            "occurrenceID": oid,
            "basisOfRecord": "MaterialSample",
            "scientificName": r.get("scientificName"),
            "scientificNameID": lsid,
            "acceptedNameUsage": r.get("acceptedScientificName"),
            "organismQuantity": r.get("reads"),
            "organismQuantityType": "DNA sequence reads" if r.get("reads") not in (None, "") else "",
            "associatedSequences": r.get("associatedSequences", ""),
            "kingdom": r.get("kingdom", ""),
            "genus": r.get("genus", ""),
        })
    occ_cols = list(occ_rows[0].keys())
    occ_content = d.write_tsv(occ_rows, occ_cols)

    # ---------------- DNA-derived data extension ----------------
    gene = manifest.get("marker", "unspecified")
    envo = {"env_broad_scale": "marine biome (ENVO:00000447)",
            "env_local_scale": "coastal water (ENVO:00001250)",
            "env_medium": "waterborne particulate matter (ENVO:01000436)"}
    dna_cols = ["eventID", "occurrenceID", "DNA_sequence", "target_gene",
                "target_subfragment", "pcr_primer_forward", "pcr_primer_reverse",
                "pcr_primer_name_forward", "pcr_primer_name_reverse",
                "pcr_primer_reference", "Pcr_cond", "annealingTemp",
                "annealingTempUnit", "ampliconSize", "env_broad_scale",
                "env_local_scale", "env_medium", "lib_layout", "seq_meth",
                "otu_class_appr", "otu_seq_comp_appr", "otu_db", "sop"]
    dna_rows = []
    for i, r in df.iterrows():
        dna_rows.append({
            "eventID": seq_ids[i],
            "occurrenceID": occ_rows[i]["occurrenceID"],
            "DNA_sequence": r.get("dna_sequence") or r.get("asv_sequence", ""),
            "target_gene": gene,
            "target_subfragment": manifest.get("target_subfragment", ""),
            "pcr_primer_forward": manifest.get("pcr_primer_forward", ""),
            "pcr_primer_reverse": manifest.get("pcr_primer_reverse", ""),
            "pcr_primer_name_forward": "manifest-provided",
            "pcr_primer_name_reverse": "manifest-provided",
            "pcr_primer_reference": manifest.get("pcr_primer_reference", ""),
            "Pcr_cond": manifest.get("pcr_cond", ""),
            "annealingTemp": manifest.get("annealing_temp", ""),
            "annealingTempUnit": "Celsius",
            "ampliconSize": manifest.get("amplicon_size", ""),
            "env_broad_scale": envo["env_broad_scale"],
            "env_local_scale": envo["env_local_scale"],
            "env_medium": envo["env_medium"],
            "lib_layout": "paired",
            "seq_meth": seq_meth_of(manifest),
            "otu_class_appr": "idtaxa;nf-edna;ASV",
            "otu_seq_comp_appr": "DADA2;nf-edna;ASV",
            "otu_db": "crosscheck taxon-resolve cache (WoRMS AphiaIDs)",
            "sop": "https://nf-core.readthedocs.io/edna (nf-edna pipeline)",
        })
    dna_content = d.write_tsv(dna_rows, dna_cols)

    # ---------------- eMoF / OBIS-ENV-DATA (Bio-ORACLE slot-in) ----------------
    env_cols = [c for c in df.columns if c.startswith("env_bio_")]
    extensions = [
        {"location": "occurrence.txt", "rowType": d.OCC_ROWTYPE,
         "columns": occ_cols, "coreid_index": 0, "coreid_term": "occurrenceID"},
        {"location": "dna_derived_data.txt", "rowType": d.DNA_ROWTYPE,
         "columns": dna_cols, "coreid_index": 0, "coreid_term": "eventID"},
    ]
    ext_files = [
        {"location": "occurrence.txt", "content": occ_content},
        {"location": "dna_derived_data.txt", "content": dna_content},
    ]
    emof_rows = []
    if env_cols:
        for i, r in df.iterrows():
            for c in env_cols:
                v = r.get(c)
                if v in (None, ""):
                    continue
                emof_rows.append({
                    "eventID": seq_ids[i],
                    "occurrenceID": occ_rows[i]["occurrenceID"],
                    "measurementType": c,
                    "measurementValue": v,
                    "measurementUnit": ("http://vocab.nerc.ac.uk/collection/P06/current/UPAA/"
                                        if "temp" in c.lower() else
                                        ("http://vocab.nerc.ac.uk/collection/P06/current/PSUU/"
                                         if "salin" in c.lower() else "")),
                    "measurementDeterminedBy": "Bio-ORACLE (occurrence-publish eMoF slot-in)",
                })
        if emof_rows:
            emof_cols = ["eventID", "occurrenceID", "measurementType", "measurementValue",
                         "measurementUnit", "measurementDeterminedBy"]
            extensions.append({"location": "emof.txt", "rowType": d.EMOF_ROWTYPE,
                               "columns": emof_cols, "coreid_index": 0,
                               "coreid_term": "eventID"})
            ext_files.append({"location": "emof.txt",
                              "content": d.write_tsv(emof_rows, emof_cols)})

    # ---------------- zip ----------------
    meta = d.build_meta_xml(
        {"location": "event.txt", "rowType": d.EVENT_ROWTYPE,
         "columns": ["eventID"] + event_cols[1:], "id_index": 0},
        extensions)
    bbox = manifest.get("bbox", [-180, -90, 180, 90])
    begin = str(df["eventDate"].min())[:10]
    end = str(df["eventDate"].max())[:10]
    eml = d.build_eml(
        title=manifest.get("title", f"eDNA Event-Core package ({ds_key}) — marine"),
        abstract=f"OBIS Event-Core eDNA package: {len(event_rows)} events, "
                 f"{len(occ_rows)} occurrences, per http://manual.obis.org/dna_data.html.",
        bbox=bbox, begin_date=begin, end_date=end,
        creator_surname=manifest.get("creator_surname", "AixBio"),
        marker=gene, taxonomic_coverage=df["scientificName"].dropna().tolist(),
        # SP-4: user_email propagated from crosscheck preflight via params.json.
        # Required by OBIS for any Event-Core package publication.
        contact_email=manifest.get("user_email"))
    zip_path = run_dir / f"{ds_key}_obis_dwca.zip"
    d.build_dwca_zip(zip_path, {"location": "event.txt", "content": event_content},
                     ext_files, eml, meta)

    cmds = work / "publish_commands.sh"
    with open(cmds, "a", encoding="utf-8") as fh:
        fh.write(f"\n# OBIS upload (user executes against an OBIS IPT, e.g. https://ipt.obis.org):\n"
                 f"#   web-upload {zip_path}  (or eDNAbridge equivalent against the OBIS IPT URL)\n")

    build = {"leg": "obis", "zip": str(zip_path), "sha256": d.sha256_of(zip_path),
             "event_rows": len(event_rows), "occurrence_rows": len(occ_rows),
             "dna_rows": len(dna_rows), "emof_rows": len(emof_rows)}
    (work / "obis_build.json").write_text(json.dumps(build, indent=2))
    print(f"[obis] built {zip_path} ({len(event_rows)} events, {len(occ_rows)} occurrences, "
          f"{len(dna_rows)} DNA rows, {len(emof_rows)} eMoF rows)")
    return 0


def seq_meth_of(manifest):
    return manifest.get("seq_meth", "Illumina iSeq 2x150")


if __name__ == "__main__":
    sys.exit(main())