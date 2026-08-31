---
name: occviz-env-profiles
description: 'Realm-routed environmental profiles and envelopes for occurrence tables (occurrence-viz profiles-env/ sub-skill, PLAN-marine-edna-meta-skill.md §5). ONE plotting code path for all realms — the x-axis variable and figure family come from the run config: marine → depth profile (depth_m / env_bio_*); freshwater/terrestrial → elevation/bioclim profile (env_wc_*, elev). Environmental envelopes per species (points + mean±95% CI); optional trait-space plot rendered ONLY when crosscheck trait columns exist (PLAN §11.6 graceful absence). Triggers: "depth profile plot", "elevation profile eDNA", "env envelope plot", "trait space plot".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "depth profile eDNA"
  - "elevation profile eDNA"
  - "env envelope plot"
  - "trait space plot"
  - "bioclim profile"
---

# Skill: occviz-env-profiles (occurrence-viz / profiles-env)

## 0. Inputs / Outputs contract

### Inputs (consumed)

| Path | Source | Required? |
| --- | --- | --- |
| occurrence table (parquet/csv/tsv) | preflight/ (validated) | yes |
| realm run config (`profiles` block: x_variables, x_label, figure_title, reverse_y, envelope_variables, envelope_label, trait_space) | run setup | yes |

### Outputs (produced)

| Path | Owner | Format | Notes |
| --- | --- | --- | --- |
| `fig/03_env_profile.png` + `.pdf` | this skill | image | occurrence distribution along x (depth / elevation) — skipped with reason when no candidate column present |
| `fig/04_env_envelope.png` + `.pdf` | this skill | image | per-species env envelopes (needs ≥1 env column, ≥3 values/species) |
| `fig/05_trait_space.png` + `.pdf` | this skill | image | OPTIONAL — only when crosscheck trait columns exist |
| `work/figure_status.jsonl` append + `work/plots/*.rds` | this skill | JSONL / RDS | consumed by report/ |

## Ask-user stop points

### SP1 — Realm profile variable
Trigger: candidate x-variable ambiguity. Evidence: `profiles.x_variables` first-hit resolution. Recommend: first present column (marine → `depth_m`/`depth`; freshwater/terrestrial → `elev`/`env_wc_elev`). Options: (A) first hit (recommended), (B) pin column, (C) drop profile.

### SP2 — Envelope statistic
Trigger: which env variables + which summary to draw. Evidence: `envelope_variables`. Recommend: jittered points + mean ± 95% CI pointrange (default). Options: (A) default, (B) 5–95% quantile ribbon, (C) boxplots (change in config/code flag).

### SP3 — Known-range overlay (marine + freshwater finfish)
Trigger: FishBase trait columns (`trait_depth_min_m/max`) present. Recommend: overlay trait depth range when a depth-profile figure is requested. Options: (A) render overlay in v2, (B) note in caption that flags come from edna-crosscheck ENVELOPE_VIOLATION only. v1 renders observed distributions; the overlay is an explicit extension point.

### SP4 — Trait-space render
Trigger: trait columns partial. Recommend: render only `trait_trophic_level` pairs available; otherwise skip (graceful).

## Description

Same functions render a marine depth profile and a terrestrial elevation/bioclim profile — realm-awareness is the run config (`x_variables`, labels, reverse_y), never code. Env/trait figures render only when their columns exist; every skip is recorded with a reason in `figure_status.jsonl` so the report can quote it (PLAN §11.6). This skill plots observations; it never computes flags — ENVELOPE_VIOLATION logic lives in edna-crosscheck.

## Procedure

```bash
pixi run profiles --input test/test_fixture_marine.parquet \
    --config config/run-config.marine.json --outdir runs/battletest_marine
# terrestrial: same command with config/run-config.terrestrial.json
```

## Troubleshooting — Signature library

| Signature in stderr / log | Likely cause | Suggested fix |
|---|---|---|
| `none of the configured profile x-variable(s) present in input` | plain obis-gbif-fetch pull without depth/elev column | expected for marine maps-only runs; add env columns via edna-crosscheck env-extract or extend `x_variables` |
| `column '...' present but only N non-numeric value(s)` | env column stored as text | coerce upstream (`enriched.parquet` dtypes per PLAN §11.2) |
| `env columns present but < 3 values per species × variable` | sparse enrichment | lower threshold at config/code (documented trade-off: noisier envelopes) |
| y-axis reversed but depth values positive | `reverse_y` mis-set for realm | marine depth: keep natural axis with x=depth; elevation configs use ascending axis — fix config |
| patchwork/as.list errors downstream | skipped figures left stale rds | `rm -rf <outdir>/work` and rerun full phase chain |
| `Error: could not find function 'sym'` | base packages stripped | run inside the pixi env (`pixi run profiles`), not bare system R without r-dplyr |

## What NOT to do

- Do **not** compute envelope flags here — edna-crosscheck owns ENVELOPE_VIOLATION; viz draws observations.
- Do **not** require trait/env columns — every figure degrades to a logged skip.
- Do **not** write per-realm plotting functions — one code path, config picks the variable.