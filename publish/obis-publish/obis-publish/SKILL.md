---
name: obis-publish
description: 'Sub-skill 3 of occurrence-publish: builds the OBIS Event-Core DwC-A (survey/cruise -> station -> sample -> sequencing event hierarchy + occurrence extension + DNA-derived data extension + eMoF/OBIS-ENV-DATA rows, linked via eventID/occurrenceID) for MARINE datasets only. Enforces HARD GATE (b): refuses with a clear message when realm != marine (OBIS does not accept terrestrial/freshwater datasets). Enforces HARD GATE (c): hard-rejects any record without a WoRMS-valid scientificNameID (urn:lsid:marinespecies.org:taxname:N). Bio-ORACLE env_* values slot in as eMoF measurementOrFact rows when present. Emits *_obis_dwca.zip + ready-to-run OBIS IPT upload command (no live push in v1). Triggers: "obis publish", "event core dwca", "OBIS-ENV-DATA", "WoRMS LSID gate".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "obis publish"
  - "event core dwca"
  - "OBIS-ENV-DATA"
  - "worms lsid gate"
  - "eMoF builder"
disable-model-invocation: true
---

# Sub-skill: obis-publish

## Inputs / Outputs contract

| Artifact | Source | Required |
|---|---|---|
| `<run-dir>/enriched.parquet` | edna-crosscheck (§11.2) | yes |
| `<run-dir>/params.json` | run manifest (§11.1) | yes |
| `work/gate_report.json` | preflight-publish | yes (`gate_a == passed`) |
| `<run-dir>/*_obis_dwca.zip` | this sub-skill | — (produced, marine only) |
| `work/publish_commands.sh` | appended OBIS IPT upload command | — (appended) |
| `work/obis_rejections.json` | this sub-skill (gate c row list) | — (produced) |

Implementation: `scripts/obis_publish.py` (shared writer: `scripts/dwca_core.py`).

## Procedure

1. **Re-check gates (a)/(b)** before touching data:
   - gate (a): `work/gate_report.json` must say `gate_a == "passed"` (or `n/a` when the
     flagged TSV is empty).
   - **HARD GATE (b)**: read `realm` from the manifest. If `realm != "marine"` → print
     `GATE-B: OBIS refuses non-marine datasets (realm="<realm>"). OBIS does not accept
     terrestrial or freshwater datasets — publish to GBIF only.` and exit non-zero without
     creating any output file.
2. **Build the Event Core hierarchy** per OBIS dna_data manual (docs-corpus/obis-dna-data/):
   - `CRU::<title>` (survey/cruise, no parentEventID; location-free) →
     `CRU::...::ST<station>` (station: decimalLatitude/Longitude, depth in meters) →
     `...::SMP<n>` (sample: sampleSizeValue/sampleSizeUnit from data, e.g. litres filtered) →
     `...::SEQ<k>` (sequencing event: samplingProtocol, eventDate, marker in protocol text).
   - `eventID`/`parentEventID` columns; `type` = Survey/…/sequencing free-text notes in
     `samplingProtocol` / `eventRemarks`.
3. **Occurrence extension**: one row per taxon × site record. `occurrenceID` (as GBIF leg),
   `basisOfRecord=MaterialSample`, `organismQuantity`+`organismQuantityType`,
   `scientificName`, `scientificNameID` = `urn:lsid:marinespecies.org:taxname:<worms_AphiaID>`,
   `kingdom`→`genus` when present, `associatedSequences`. Linked via `eventID` (coreid).
4. **HARD GATE (c)**: for every occurrence row, `scientificNameID` must match
   `^urn:lsid:marinespecies\.org:taxname:\d+$`. Any row failing → collect into
   `work/obis_rejections.json` (row, scientificName, missing reason) and **hard-reject**:
   the leg exits non-zero and produces NO zip until WoRMS IDs are backfilled (rerun
   crosscheck taxon-resolve) or the user maps unassigned taxa to
   `Biota incertae sedis` LSID `urn:lsid:marinespecies.org:taxname:12`. No warnings-only path.
5. **DNA-derived data extension**: rows keyed on `occurrenceID` (+ `eventID`), terms per
   docs-corpus/dna-derived-data-extension/README.md.
6. **eMoF / OBIS-ENV-DATA**: for each `env_bio_*` column present in enriched.parquet (Bio-ORACLE
   Phase-1 output), one measurementOrFact row per occurrence: measurementType = layer name,
   measurementValue = value, measurementUnit = NERC P06 URI for known units (temp °C/salinity PSU
   defaults). If no env columns → omit the eMoF file and its meta.xml entry entirely.
7. **meta.xml + eml.xml + zip** via `dwca_core` (core rowType = Event). Output
   `*_obis_dwca.zip`. Append OBIS IPT upload command to `work/publish_commands.sh`:
   ```bash
   # upload to an OBIS IPT (https://ipt.obis.org) — USER EXECUTES:
   # IPT web upload of <zip path>, or eDNAbridge equivalent against the OBIS IPT URL.
   ```
8. Write `work/obis_build.json` (event/occurrence/extension row counts, sha256).

## Interpretation Guidelines

- **GO**: marine; all rows pass gate (c); hierarchy connects; zip emitted.
- **NO-GO**: any of — gate (b) refusal, gate (c) rejections non-empty, gate (a) blocked.
- There is deliberately **no GO-WITH-WARNINGS** for the LSID gate (pinned: hard-reject).

## Ask-user stop points

| SP | Trigger | Resolution record |
|---|---|---|
| SP-O1 | realm != marine | Hard gate (b) — pinned refusal, never ask to override. |
| SP-O2 | Missing WoRMS LSID | Hard gate (c) — pinned hard-reject; remediation path in report. |
| SP-O3 | eMoF env columns absent | Auto-omit eMoF (pinned: "else omit" — no ask). |

## Troubleshooting — Signature library

| Signature | Likely cause | Suggested fix |
|---|---|---|
| `GATE-B: OBIS refuses` | realm is freshwater/terrestrial | GBIF-only publish; redeclare marine at crosscheck preflight if the dataset really is marine. |
| `GATE-C: N record(s) without a WoRMS-valid scientificNameID` | AphiaIDs missing | Backfill crosswalk; or map unresolved to Biota incertae sedis LSID 12 (see docs-corpus). |
| `parentEventID not in eventID set` | Hierarchy builder bug | `pixi run test-smoke` then debug-report.md. |
| eMoF file appears despite no env columns | env prefix mismatch vs manifest | Check `env_column_prefix.bio_oracle` in the run manifest. |
| `duplicate eventID` | Two stations share a name+date | Distinguishing suffixes are auto-appended; if you see this the builder failed — report. |

## Output contract

`*_obis_dwca.zip` + `work/obis_rejections.json` (if gate c fired) + appended
`work/publish_commands.sh` + `work/obis_build.json`. Next sub-skill:
`validate/validate-dwca/SKILL.md`.