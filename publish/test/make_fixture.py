#!/usr/bin/env python3
"""Build the SYNTHETIC battle-test fixture (PLAN §11.2/§11.4; §11.8 rule 4).

Synthetic marine-fixture status is recorded in battle-test-report.md.

Writes into a scenario run dir:
  params.json (run manifest §11.1) + enriched.parquet (§11.2) + flagged_occurrences.tsv (§11.4)

Options:
  --out DIR            scenario run dir
  --realm R            marine|freshwater|terrestrial (default marine)
  --signoff S          pending|approved|excluded|mixed (default approved)
  --missing-aphia N    make N rows lack worms_AphiaID (gate c scenario; default 0)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROWS = [
    # site fields
    dict(eventDate="2026-07-01", decimalLatitude=36.83, decimalLongitude=21.31,
         minimumDepthInMeters=10, maximumDepthInMeters=40, filter_volume_l=100),
    dict(eventDate="2026-07-02", decimalLatitude=37.40, decimalLongitude=15.62,
         minimumDepthInMeters=50, maximumDepthInMeters=90, filter_volume_l=120),
    dict(eventDate="2026-07-02", decimalLatitude=37.40, decimalLongitude=15.62,
         minimumDepthInMeters=50, maximumDepthInMeters=90, filter_volume_l=120),
    dict(eventDate="2026-07-03", decimalLatitude=-33.91, decimalLongitude=18.42,
         minimumDepthInMeters=5, maximumDepthInMeters=25, filter_volume_l=80),
    dict(eventDate="2026-07-03", decimalLatitude=-33.91, decimalLongitude=18.42,
         minimumDepthInMeters=5, maximumDepthInMeters=25, filter_volume_l=80),
]

TAXA = [
    # scientificName, accepted, gbif, aphia, status, kingdom, genus
    ("Gadus morhua", "Gadus morhua", 2476942, 126431,  "resolved", "Animalia", "Gadus"),
    ("Engraulis encrasicolus", "Engraulis encrasicolus", 2413312, 127188, "resolved",
     "Animalia", "Engraulis"),
    ("Micromesistius poutassou", "Micromesistius poutassou", 2413322, 127205, "resolved",
     "Animalia", "Micromesistius"),
    ("Sardina pilchardus", "Sardina pilchardus", 2413260, 127005, "resolved",
     "Animalia", "Sardina"),
    ("Novelus asvus", "", None, None, "NOVEL_TAXON", "Animalia", "Novelus"),
]


def build(out: Path, realm: str, signoff: str, missing_aphia: int):
    out.mkdir(parents=True, exist_ok=True)
    for p, d in (("env_bio_", [15.6, 12.4, 12.4, 18.1, 18.1]),
                 ("_sal", [38.2, 38.6, 38.6, 35.4, 35.4])):
        pass
    env_temp = [15.6, 12.4, 12.4, 18.1, 18.1]
    env_sal = [38.2, 38.6, 38.6, 35.4, 35.4]
    rows = []
    for i, (site, tax) in enumerate(zip(ROWS, TAXA)):
        r = dict(site)
        r.update(dict(
            scientificName=tax[0], acceptedScientificName=tax[1],
            gbif_taxonKey=tax[2], worms_AphiaID=tax[3],
            taxon_match_status=tax[4], kingdom=tax[5], genus=tax[6], taxonRank="species",
            trait_depth_min_m=0.0, trait_depth_max_m=300.0, trait_trophic_level=3.5,
            trait_body_size_cm=45.0,
            fishbase_SpeCode=(i + 1),
            env_bio_temp_ss=env_temp[i], env_bio_salinity_ss=env_sal[i],
            env_layer_class="surface", qc_flags="", qc_level="ok", realm=realm,
            asv_id=f"asv{i + 1}", dna_sequence="ACGTACGTACGTACGTACGT",
            reads=1000 + 137 * i, total_reads=15234 + 71 * i,
            associatedSequences="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA000000",
        ))
        rows.append(r)
    df = pd.DataFrame(rows)
    # §11.2 base rows are real-number floats where numeric
    df["gbif_taxonKey"] = df["gbif_taxonKey"].astype("Int64")
    df["worms_AphiaID"] = df["worms_AphiaID"].astype("Int64")
    df["fishbase_SpeCode"] = df["fishbase_SpeCode"].astype("Int64")
    df.to_parquet(out / "enriched.parquet", index=False)

    # ---- flagged rows: the NOVEL_TAXON row + one ENVELOPE_VIOLATION row on Gadus
    flagged = []
    for i, r in enumerate(rows):
        if r["qc_level"] != "ok":
            raise AssertionError("fixture sanity")
    # create flags: row 4 (novel taxon) + decorate row 0 as ENVELOPE_VIOLATION example
    rows[4]["qc_flags"] = "NOVEL_TAXON;GENUS_ONLY"
    rows[4]["qc_level"] = "warning"
    df.loc[4, "qc_flags"] = "NOVEL_TAXON;GENUS_ONLY"
    df.loc[4, "qc_level"] = "warning"
    rows[0]["qc_flags"] = "ENVELOPE_VIOLATION"
    rows[0]["qc_level"] = "error"
    df.loc[0, "qc_flags"] = "ENVELOPE_VIOLATION"
    df.loc[0, "qc_level"] = "error"
    df.to_parquet(out / "enriched.parquet", index=False)

    # gate c scenario: strip AphiaIDs on last `missing_aphia` rows (incl. novel taxon)
    if missing_aphia > 0:
        df.loc[df.index[-missing_aphia:], "worms_AphiaID"] = pd.NA
        df["worms_AphiaID"] = df["worms_AphiaID"].astype("Int64")
        df.to_parquet(out / "enriched.parquet", index=False)

    def flag_row(i):
        r = rows[i].copy()
        for k in ("trait_depth_min_m", "trait_depth_max_m", "trait_trophic_level",
                  "trait_body_size_cm", "fishbase_SpeCode"):
            r.pop(k, None)
        return r

    flagged_idx = [0, 4]
    status = {
        "pending": lambda i: "pending",
        "approved": lambda i: "approved",
        "excluded": lambda i: "excluded",
        "mixed": lambda i: ("approved" if i == 0 else "pending"),
    }[signoff]
    with open(out / "flagged_occurrences.tsv", "w", encoding="utf-8", newline="") as fh:
        cols = list(flag_row(0).keys()) + ["signoff_status"]
        fh.write("\t".join(cols) + "\n")
        for i in flagged_idx:
            r = flag_row(i)
            r["signoff_status"] = status(i)
            fh.write("\t".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

    manifest = {
        "skill_run": "edna-crosscheck",
        "realm": realm,
        "marker": "12S",
        "target_subfragment": "12S-Fish",
        "dataset_key": "SYNTH001",
        "title": "Synthetic marine eDNA battle-test fixture (occurrence-publish)",
        "bbox": [15.0, -34.5, 22.0, 38.0],
        "env_source": {"marine": "bio-oracle-v3"},
        "env_layers": {"bio_oracle": ["BO2_tempmin_ss", "BO2_salinitymean_ss"]},
        "env_scenario": "present",
        "backbones": {"gbif": True, "worms": "marine-only", "fishbase": True},
        "obis_lookup": realm == "marine",
        "env_column_prefix": {"bio_oracle": "env_bio_", "worldclim_chelsa": "env_wc_"},
        "pcr_primer_forward": "GTCGGTAAAACTCGTGCCAGC",
        "pcr_primer_reverse": "CATAGTGGGGTATCTAATCCCAGTTTG",
        "seq_meth": "Illumina iSeq 2x150",
    }
    (out / "params.json").write_text(json.dumps(manifest, indent=2))
    print(f"[fixture] wrote {out} (realm={realm}, signoff={signoff}, missing_aphia={missing_aphia})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--realm", default="marine")
    ap.add_argument("--signoff", default="approved")
    ap.add_argument("--missing-aphia", type=int, default=0)
    a = ap.parse_args()
    build(Path(a.out), a.realm, a.signoff, a.missing_aphia)