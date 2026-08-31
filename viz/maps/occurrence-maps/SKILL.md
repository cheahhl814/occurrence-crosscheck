---
name: occviz-occurrence-maps
description: 'Species occurrence maps for DwC-shaped occurrence tables (occurrence-viz maps/ sub-skill, PLAN-marine-edna-meta-skill.md §5). rnaturalearth basemap (medium via rnaturalearthdata) with the AMPLICON geocurate_inventory.R fallback chain (maps::map("world") → bare frame), fixed-seed (42) point subsampling to map_points_max, per-species facet small-multiples, realm-agnostic colouring from run config. 300-dpi PNG + vector PDF outputs. Triggers: "occurrence map eDNA", "plot gbif obis records", "species occurrence map".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "occurrence map eDNA"
  - "plot gbif obis records"
  - "species occurrence map"
  - "rnaturalearth map"
---

# Skill: occviz-occurrence-maps (occurrence-viz / maps)

## 0. Inputs / Outputs contract

### Inputs (consumed)

| Path | Source | Required? |
| --- | --- | --- |
| occurrence table (parquet/csv/tsv, PLAN §11.6 minimal DwC) | preflight/ (validated) | yes |
| realm run config JSON (`map` block: palette, coastline, coast_scale, max_points, max_species) | run setup | yes |

### Outputs (produced)

| Path | Owner | Format | Notes |
| --- | --- | --- | --- |
| `fig/01_occurrence_map.png` + `.pdf` | this skill | image | all-species overview, colour = species |
| `fig/02_species_maps.png` + `.pdf` | this skill | image | small multiples, top-N species (skipped with reason when ≤1 species) |
| `<outdir>/work/figure_status.jsonl` append + `<outdir>/work/plots/*.rds` | this skill | JSONL / RDS | consumed by report/ |

## Ask-user stop points

### SP1 — Extent / bbox
Trigger: huge lat/lon spread or antimeridian crossing. Evidence: coordinate range. Recommend: data-driven extent (default). Options: (A) data extent, (B) explicit `map.bbox` in config, (C) regional split.

### SP2 — Subsampling cap
Trigger: > `max_points` (default 20,000) points. Evidence: geocurate pattern — subsample with `set.seed(42)` and record counts in the subtitle. Options: (A) subsample at 20k (recommended), (B) plot all (slow, overlapping), (C) hex-bin density instead (not in v1 — record as extension).

### SP3 — Basemap resolution / source
Trigger: `coastline` choice. Recommend `auto` (rnaturalearth medium → maps::map() fallback). Options: (A) auto (recommended), (B) force rnaturalearth, (C) force maps (lighter, low-res). `rnaturalearthhires` is NOT packaged on conda-forge — high-res is an explicit local install, not a pixi dep.

### SP4 — Species panel set
Trigger: > `max_species` species for small multiples. Recommend: top-N by record count (default 12). Options: (A) top-N, (B) alphabetical, (C) a fixed species list via config.

## Description

Renders occurrence maps with ggplot2 + sf geometry. The basemap follows the workspace-proven geocurate_inventory.R fallback chain so the skill never hard-fails on a missing high-res dataset, and points are subsampled with a fixed seed for reproducibility. Points colored per species (`map.palette`); marine runs get a log line noting the on-land visual sanity check (flagging itself lives in edna-crosscheck).

## Procedure

```bash
pixi run maps --input test/test_fixture_marine.parquet \
    --config config/run-config.marine.json --outdir runs/battletest_marine \
    --input-label "synthetic marine fixture"
```

## Troubleshooting — Signature library

| Signature in stderr / log | Likely cause | Suggested fix |
|---|---|---|
| `Error in st_crop ... / empty map` | bbox does not intersect coastline polygons | widen `map.bbox` or drop bbox (data extent) |
| `rnaturalearth not available; falling back to maps::map()` | rnaturalearthdata missing | expected fallback (geocurate pattern); install r-rnaturalearthdata in pixi.toml for medium scale |
| `crs not found: is it missing?` / map renders but points missing | PROJ database unresolved OR points outside bbox / subsampled away | PROJ: see the `PROJ_DATA init` note in `bin/lib_viz.R` (conda-forge proj ≥9 no longer ships conda activate scripts); points: enlarge extent, raise `max_points`, check coordinate order |
| `Coordinate system already present` warning | add `coord_sf()` twice | remove manual `coord_fixed` — coord_sf is fixed in code |
| garbled species facet labels | scientificName with author strings | plot uses raw names; clean via edna-crosscheck acceptedScientificName and point config at the column |
| `cannot open file 'fig/...': permissions` | outdir read-only or path missing | pass `--outdir` with write permission; dirs auto-created |
| PDF device error `cannot open file ... cairo` in non-pixi R | cairo backend unavailable | use pixi env R (r-base conda build ships cairo support) or set `output_formats: ["png"]` |

## What NOT to do

- Do **not** hard-depend on rnaturalearthhires (not on conda-forge) — fallback chain is the supported path.
- Do **not** change the subsample seed — reproducibility of the map is pinned (seed 42 per geocurate pattern).
- Do **not** add realm if-statements — basemap/extent/colour choices come from the run config only.