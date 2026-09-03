---
name: occviz-figure-report
description: 'Multi-panel publication report + auto-generated figure captions manifest for occurrence-viz (report/ sub-skill, PLAN-marine-edna-meta-skill.md §5). Assembles patchwork multi-panel overview from per-figure ggplot snapshots, writes fig/figure-captions.md (markdown captions manifest with per-figure file lists and record counts) and figure-report.md (run summary incl. gracefully skipped figures). Consumes work/figure_status.jsonl ledger. Triggers: "occurrence viz report", "figure captions manifest", "multispecies panel figure".'
version: 1.0.2
updated: "2026-08-31"
triggers:
  - "figure captions manifest"
  - "occurrence viz report"
  - "multipanel occurrence figure"
---

# Skill: occviz-figure-report (occurrence-viz / report)

## 0. Inputs / Outputs contract

### Inputs (consumed)

| Path | Source | Required? |
| --- | --- | --- |
| `<outdir>/work/figure_status.jsonl` | maps/ + profiles-env/ workers | yes (refuses to run without it) |
| `<outdir>/work/plots/*.rds` ggplot snapshots | maps/ + profiles-env/ workers | ≥1 (≥2 for the multi-panel figure) |
| realm run config JSON | run setup | yes |

### Outputs (produced)

| Path | Owner | Format | Notes |
| --- | --- | --- | --- |
| `fig/06_multispecies_overview.png` + `.pdf` | this skill | image | patchwork combination (skipped with reason when <2 panels) |
| `fig/figure-captions.md` | this skill | markdown | captions manifest: numbered captions + file list + records represented per figure |
| `figure-report.md` | this skill | markdown | run summary: input, realm, rendered/skipped with reasons |
| `work/figure_status.jsonl` append | this skill | JSONL | manifest record |

## Ask-user stop points

### SP1 — Panel composition
Trigger: which saved panels enter the multi-figure. Evidence: figures rendered in the ledger. Recommend: all except the facet grid (02) which dominates layout. Options: (A) default composition, (B) all panels, (C) explicit subset in config.

### SP2 — Caption voice
Trigger: captions target audience. Recommend: neutral start-point captions with method note (auto-generated). Options: (A) auto captions (recommended — edit freely), (B) terse labels only, (C) full methods sentence per figure (documented manual edit).

### SP3 — Output bundle
Trigger: what ships after the run. Evidence: figure-report.md + figure-report dir contents. Recommend: bundle `fig/` + `figure-report.md` only (`work/` stays scratch). Options: (A) default bundle, (B) include .rds snapshots, (C) PDF-only bundle.

## Description

The report/ sub-skill closes the run: it turns the per-figure status ledger (including graceful skips with reasons) into the auto-generated captions manifest and a human-readable run report, and assembles the multi-panel overview with patchwork. It is purely local: no network, no API calls, deterministic given the same .rds snapshots.

## Procedure

```bash
pixi run report --config config/run-config.marine.json --outdir runs/battletest_marine \
    --input test/test_fixture_marine.parquet --input-label "synthetic marine fixture"
cat runs/battletest_marine/fig/figure-captions.md
```

## Troubleshooting — Signature library

| Signature in stderr / log | Likely cause | Suggested fix |
|---|---|---|
| `no work/figure_status.jsonl found — run plot_map.R and plot_profiles.R first` | report run before plotting workers | rerun maps + profiles phases, or the full `pixi run viz` chain |
| `only N saved panel(s); need >= 2 ggplot objects` | profile figures skipped (missing columns) on a minimal table | expected; the manifest + report still ship |
| `Error in switch(as.character(r$figure)...` | unexpected figure id in status ledger | ledger entries are append-only; `rm <outdir>/work/figure_status.jsonl` and rerun phases in order |
| patchwork combo taller than allowed height | many panels stacked at 5.2 in each | height clamps at 24 in; reduce panel set or rerender panels smaller |
| captions reference missing files | figures deleted after render | keep `fig/` intact until after report generation |
| `object 'exg' not found` / NA captions | ledger record without `extra` JSON | re-run the producing worker; ledger is append-only |

## What NOT to do

- Do **not** hand-edit `work/figure_status.jsonl` — append-only ledger; delete and re-run instead.
- Do **not** fabricate record counts in captions — they come from the ledger metadata.
- Do **not** treat skipped figures as failures — they are the documented §11.6 graceful-absence behavior.