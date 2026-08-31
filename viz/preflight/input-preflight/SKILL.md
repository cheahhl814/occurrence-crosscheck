---
name: occviz-input-preflight
description: 'Validate the input occurrence table and realm run config before any figure rendering (occurrence-viz Phase 2 of the marine-eDNA stack). Checks the PLAN §11.6 standalone contract: required DwC columns scientificName / decimalLatitude / decimalLongitude / eventDate; env+trait columns optional and gracefully absent. Emits a run preflight summary (records, species, date range, available profile x-variable, present env vars) and gates figure rendering on ≥1 renderable figure family. Triggers: "occurrence viz preflight", "validate dwc table for plotting", "occurrence viz run config".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "occurrence viz preflight"
  - "validate dwc table for plotting"
  - "occurrence viz run config"
  - "realm run config check"
---

# Skill: occviz-input-preflight (occurrence-viz / preflight)

## 0. Inputs / Outputs contract

### Inputs (consumed)

| Path | Source | Required? |
| --- | --- | --- |
| occurrence table: parquet (arrow) / csv / tsv with minimal DwC columns (PLAN §11.6) | upstream: obis-gbif-fetch, edna-crosscheck `enriched.parquet`, or any DwC-shaped file | yes |
| realm run config JSON (`config/run-config.{marine,freshwater,terrestrial}.json` or a copy) | run setup | yes |
| `--input-label` | run setup | optional |

### Outputs (produced)

| Path | Owner | Format | Notes |
| --- | --- | --- | --- |
| run preflight summary (stdout) | this skill | text | records, species, date range, available optional columns |
| `<outdir>/work/figure_status.jsonl` (preflight record) | this skill | JSONL | consumed by report/ |

**Verdict gate**: rendering refuses to start if any required DwC column is missing or all coordinates are invalid.

## Ask-user stop points (Evidence + Recommend + Options)

Stop points fire only when evidence is ambiguous; when the run is fully specified they auto-resolve and are logged to preflight.md.

### SP1 — Figure set selection
Trigger: caller did not say which figures to produce. Evidence: config `figures` block. Recommend: the config defaults (map + realm-routed profile + envelopes). Options: (A) use config defaults (recommended), (B) maps only, (C) custom subset.

### SP2 — Output formats
Trigger: `output_formats` absent/invalid. Recommend `["png","pdf"]` (300-dpi PNG + vector PDF, pinned baseline). Options: (A) png+pdf (recommended), (B) +svg (requires svglite), (C) png only.

### SP3 — Palette / map choices
Trigger: `map.palette` missing. Recommend perceptually-uniform CVD-safe defaults (`viridis`, or `scico:batlow`). Options: (A) viridis, (B) scico:<name>, (C) custom hexes (edit config).

### SP4 — Ambiguous realm
Trigger: config `realm` is not marine/freshwater/terrestrial, or the input's coordinates contradict the declared realm (marine config but no record within ~50 km of coastline is a WARNING, not an error — coordinate-realm consistency per PLAN risk #8). Recommend: re-declare realm and rerun.

### SP5 — Depth/elevation column choice
Trigger: several candidate x-variables present. Recommend the first hit of `profiles.x_variables` (logged). Options: (A) accept first hit, (B) pin one column in config, (C) skip profiles.

## Description

Validates the input table against the standalone contract (PLAN §11.6): `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate` REQUIRED; everything else OPTIONAL (env/trait figures render only when their columns exist). Loads the realm run config (realm is a dataset-level declaration). Emits the run preflight summary and the first `figure_status.jsonl` record. Deliberately light: no API calls, no flags — flagging lives in edna-crosscheck; visualization is observational.

## Procedure

```bash
cd <skill-dir>
# Quick preflight only (no figures):
pixi run Rscript bin/viz_run.R --input data/enriched.parquet \
    --config config/run-config.marine.json --outdir runs/2026-08-31_malacca --phase preflight
# Full run (preflight + figures):
pixi run viz --input data/enriched.parquet --config config/run-config.marine.json \
    --outdir runs/malacca_2026-08-31 --input-label "Malacca eDNA 2026-08"
```

## Troubleshooting — Signature library

| Signature in stderr / log | Likely cause | Suggested fix |
|---|---|---|
| `missing required DwC column(s): ...` | input lacks PLAN §11.6 minimal columns | fix upstream export (obis-gbif-fetch/crosscheck) or rename columns; do NOT rename in viz — the contract is pinned |
| `unsupported input extension` | input is not parquet/csv/tsv | convert (arrow::write_parquet) or export CSV |
| `dropping N row(s) with invalid/out-of-range coordinates` | lat/lon swaps or 0-fill placeholders upstream | recheck upstream QC (obis-data-qc / edna-crosscheck ON_LAND); viz only warns and drops |
| `none of the configured profile x-variable(s) present` | env/trait columns absent — normal for plain obis-gbif-fetch pulls | expected graceful absence; figure is skipped with reason, map still renders |
| `Error in fromJSON: ...` | run config JSON malformed | validate with `python3 -m json.tool <config>`; start from `config/run-config.<realm>.json` |
| `no rows with valid coordinates after validation` | wrong column mapping (lat/lon swapped) | verify `decimalLatitude`/`decimalLongitude` are not transposed upstream |

## What NOT to do

- Do **not** flag or drop records based on value ranges — viz never flags; that is edna-crosscheck's job.
- Do **not** branch on realm inside plotting code — realm lives only in the run config.
- Do **not** require env/trait columns — their absence is an expected, logged skip.