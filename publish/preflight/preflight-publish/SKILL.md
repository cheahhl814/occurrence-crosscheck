---
name: preflight-publish
description: 'Sub-skill 1 of occurrence-publish: validates the §11.7 input contract (enriched.parquet §11.2, flagged_occurrences.tsv §11.4, run manifest §11.1) and enforces HARD GATE (a) — flagged_occurrences.tsv rows with signoff_status == pending hard-block publish; aborts with a per-row report until every row is approved/excluded. Emits work/gate_report.json and work/publish_commands.sh skeleton. Triggers: "publish preflight", "sign-off gate", "validate publish inputs".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "publish preflight"
  - "sign-off gate"
  - "validate publish inputs"
  - "flagged occurrences sign-off"
disable-model-invocation: true
---

# Sub-skill: preflight-publish

## Inputs / Outputs contract

| Artifact | Source | Required |
|---|---|---|
| `<run-dir>/enriched.parquet` | edna-crosscheck (PLAN §11.2) | yes |
| `<run-dir>/flagged_occurrences.tsv` | edna-crosscheck (PLAN §11.4) | yes |
| `<run-dir>/params.json` | edna-crosscheck run manifest (PLAN §11.1) | yes |
| `work/gate_report.json` | this sub-skill | — (produced) |
| `work/publish_commands.sh` | this sub-skill (skeleton; publish legs append) | — (produced) |

Implementation: `scripts/op_preflight.py` (invoked as `pixi run publish-preflight --run-dir <dir> --work .`).

## Procedure

1. **Load the run manifest** (`params.json`): `realm` must be one of
   `marine|freshwater|terrestrial` (dataset-level, per PLAN scope banner). Load `marker`,
   `bbox`, `env_column_prefix` — these feed the eMoF and EML builders downstream.
2. **Validate `enriched.parquet`** against the §11.2 column contract. Hard-required for publish:
   `scientificName`, `acceptedScientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate`,
   `taxon_match_status`, `qc_flags`, `qc_level`, `realm`. Warn on missing optional columns
   (`gbif_taxonKey`, `worms_AphiaID`, `fishbase_SpeCode`, `trait_*`, `env_*` — absence changes
   extension content, never a hard failure, except the OBIS LSID gate below).
3. **Validate `flagged_occurrences.tsv`** = subset of enriched rows with `qc_level != "ok"`,
   plus `signoff_status` ∈ {`pending`, `approved`, `excluded`}.
4. **HARD GATE (a)**: if any row has `signoff_status == "pending"` →
   exit non-zero with a per-row report (row index, scientificName, qc_flags). Downstream
   publish legs re-read `gate_report.json` and refuse if `gate_a == "BLOCKED"`.
   Ask-user framing used in interactive mode (Evidence + Recommend + Options):
   > **Evidence** N pending rows, listed in the gate report.
   > **Recommend** review each and set approved (keep) or excluded (drop).
   > **Options**: (A) I set them myself and re-run; (B) show me the rows now.
   In autonomous mode this never blocks — it aborts (the gate is the point), and the battle
   test proves both directions.
5. Declare target platforms per dataset: GBIF (any realm) + OBIS (only if realm == marine).
6. Write `work/gate_report.json`: per-gate verdicts (`gate_a`, `gate_b`, `gate_c`), input paths,
   row counts, and the flag-summary counts. Write the `work/publish_commands.sh` skeleton
   (header + GBIF/OBIS upload commands appended later by the publish sub-skills).

## Interpretation Guidelines

- **GO** (gate_a = passed): proceed to gbif-publish and (if marine) obis-publish.
- **BLOCKED**: sign-off incomplete — nothing downstream may run. This is a recoverable stop,
  not an error: fix flagged_occurrences.tsv and re-run.

## Ask-user stop points

| SP | Trigger | Resolution record |
|---|---|---|
| SP-P1 | Pending flagged rows exist | Hard gate (a) — pinned; abort with report. No interactive override exists by design. |
| SP-P2 | Target platform | GBIF always; OBIS iff realm == marine (pinned hard gate b) |
| SP-P3 | Enriched parquet with rows lacking `realm` column | Fall back to manifest `realm`; record fallback in gate report |

## Troubleshooting — Signature library

| Signature | Likely cause | Suggested fix |
|---|---|---|
| `GATE-A: N pending flagged record(s)` | Users haven't signed off | Edit flagged_occurrences.tsv; set approved/excluded; re-run. |
| `missing required column: X (PLAN §11.2)` | Upstream crosscheck version mismatch | Re-run edna-crosscheck; do not hand-patch parquet. |
| `[Errno 2] enriched.parquet` | Wrong --run-dir | Point --run-dir at the crosscheck output dir. |
| `unknown signoff_status: X` | Manual edit typo | Allowed values: pending, approved, excluded. |

## Output contract

`work/gate_report.json` (machine) + console report (human). Nothing else. Next sub-skill:
`gbif-publish/gbif-publish/SKILL.md`.