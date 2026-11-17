---
name: occurrence-viz
description: "PHASE 2 of the marine-eDNA meta-skill stack (PLAN-marine-edna-meta-skill.md §5): standalone, realm-aware visualization of DwC-shaped occurrence tables — ONE interactive species occurrence map (R leaflet, self-contained single-file HTML; v1.9.0 replaces the retired rnaturalearth/ggplot2 static maps), realm-routed environmental profiles, per-species env envelopes, and optional trait-space plots, closed by a multi-panel report + auto-generated figure captions manifest. Input contract §11.6: standalone — minimal DwC columns (scientificName, decimalLatitude, decimalLongitude, eventDate) required; env/trait columns optional and gracefully absent. Works on plain obis-gbif-fetch parquet, not just edna-crosscheck output. Visualizes observations, never flags — flagging lives in edna-crosscheck. Use when the user asks to 'plot occurrence data', 'map gbif/obis records', 'make depth/elevation profiles for eDNA species', 'env envelope plot', or 'publication figures from enriched.parquet'."
version: 1.9.1
updated: "2026-11-11"
triggers:
  - "occurrence visualization"
  - "species occurrence map"
  - "plot gbif obis data"
  - "depth profile plot"
  - "elevation profile eDNA"
  - "env envelope plot"
  - "figure captions eDNA"
  - "realm-aware occurrence viz"
requires:
  - "pixi (pixi install from this skill's pixi.toml — R 4.3+ via conda-forge)"
  - "R packages: leaflet, htmlwidgets, webshot2 (map), ggplot2, sf, rnaturalearth(+data), maps, arrow, scico, viridis, patchwork, scales, optparse, dplyr, tidyr, readr, jsonlite"
  - "no network access — fully local, no API calls, no tile servers"
disable-model-invocation: true
---

# Skill: occurrence-viz

Realm-aware, standalone publication-quality occurrence visualization. This file is a **router** — the sub-skills do the work. Built with the skill-forge meta-skill per the BettaMt / AiX-BIO convention (preflight → build → debug → battle-test evidence chain; explicit ask-user stop points; signature libraries; docs-corpus).

## The realm rule (READ FIRST)

**Realm-awareness is a run-config concern, never a code concern.** One plotting code base; the realm run config (`config/run-config.<realm>.json`) picks the x-axis variable and figure family:

| Realm config | Profile x-variable (first present wins) | Notes |
|---|---|---|
| `run-config.marine.json` | `depth_m` → `depth` → `env_bio_depth_m` | depth profile; on-land visual sanity note on maps |
| `run-config.freshwater.json` | `elev` → `elevation` → `env_wc_elev` → `trait_depth_min_m` | elevation/bioclim; riparian on-land records normal |
| `run-config.terrestrial.json` | `elev` → `elevation` → `env_wc_elev` → `env_wc_bio1` | elevation/bioclim envelope; on-land is normal |

Every plotting script branches on the **config**, never `if (realm == ...)`. Realm is a dataset-level declaration (PLAN §2 SCOPE banner).

Sub-skill registry (frontmatter names): `occviz-input-preflight` (preflight/input-preflight), `occviz-occurrence-maps` (maps/occurrence-maps), `occviz-env-profiles` (profiles-env/env-profiles), `occviz-figure-report` (report/figure-report).

## Input contract (PINNED — PLAN §11.6)

```
required: scientificName | decimalLatitude | decimalLongitude | eventDate
optional (figures render only when columns exist):
  env_bio_* | env_wc_*  (crosscheck env-extract, prefixed per §11.1)
  trait_depth_min_m | trait_depth_max_m | trait_trophic_level | trait_body_size_cm
  gbif_taxonKey | worms_AphiaID | qc_flags | qc_level | env_layer_class | acceptedScientificName
```

Any parquet/CSV/TSV meeting the minimal contract works: **plain `obis-gbif-fetch` output** (maps render immediately — env/trait figures skip with a logged reason) **or** `edna-crosscheck` `enriched.parquet` (full figure set when columns are populated).

**This skill never flags.** `ENVELOPE_VIOLATION` / `OUT_OF_RANGE` / `ON_LAND` flags are edna-crosscheck's job; viz draws observations so a human can judge flags.

## 0.5 Ask-User Stop Points (runtime parameters)

> **SP-11 (echo) — Concordance ring R (`--near-km`).** Evidence: the report generator hard-fails
> (exit 2) if this run's ring does not equal the crosscheck run's ring — the merged-ring semantics
> (crosscheck/SKILL.md v2.5.1) require map ring = concordance threshold across both skills.
> This is confirm-not-choose: echo the ring already pinned by crosscheck's SP-11 (crosscheck/SKILL.md
> §0.5), don't re-derive it here.
> Auto-pick condition: never — always read and echo the upstream `params.json`/`crosscheck_report.json`
> ring value; a mismatch must fail loudly (exit 2), not silently drift. SP-10's buffer-scale backstop
> (`preflight.py --require-confirm`, crosscheck/SKILL.md §0.5) is the upstream companion check — a
> tight auto buffer on the crosscheck side produces the same false-DISCORDANT pattern this ring echo
> is meant to keep visible on the map.

> **SP-15 — Context-fetch budget (`context_records --buffer-km 500 --per-species 200 --outside-cap`).**
> Evidence: default budget (500 km / 200 records-per-species) covers the typical single-run taxa
> count without excessive fetch time. Recommend: keep defaults for runs under ~100 taxa. Confirm or
> pick one of: A) defaults (`--buffer-km 500 --per-species 200`) B) lean outside-cap
> (`--outside-cap 100`) C) heavy (`--outside-cap 1000`) for exhaustive context maps.
> Auto-pick condition: auto-pick A (defaults) when taxa count < 100; ask when the run has >=100 taxa,
> since the fetch cost and map density both scale with taxa count at that point.

> **SP-16 — Genus-narrow cutoffs (`--buffer-km 100`, `max_sp 40`).** Evidence: the default candidate
> cap (40 species per genus) is generous enough that most genera never hit it. Recommend: keep
> defaults. Confirm or pick one of: A) raise the cap B) accept with a truncation flag noted in the
> report.
> Auto-pick condition: auto-pick defaults; ask only when a genus actually hits the `max_sp` cap during
> the run (truncation would otherwise happen silently).

## Pipeline — 4 sub-skills (phase detection: state of the run's `outdir/`)

| # | Phase | Goal | Sub-skill | Outputs |
|---|---|---|---|---|
| 1 | Preflight | Validate input + config; run summary; figure-set feasibility | `preflight/input-preflight/SKILL.md` | preflight summary + `work/figure_status.jsonl` |
| 2 | Maps | ONE interactive occurrence map (R leaflet) | `maps/occurrence-maps/SKILL.md` | `fig/01_occurrence_map.html` (self-contained single file) + `fig/01_occurrence_map.png` (best-effort snapshot) |
| 3 | Profiles | Realm-routed profile + envelopes + (optional) trait space | `profiles-env/env-profiles/SKILL.md` | `fig/03_*`, `fig/04_*`, `fig/05_*` (skips logged) |
| 4 | Report | Multi-panel overview + captions manifest + run report | `report/figure-report/SKILL.md` | `fig/06_*`, `fig/figure-captions.md`, `figure-report.md` |

Run everything:

```bash
pixi install                                    # once
pixi run viz --input <table.parquet> \
    --config config/run-config.marine.json \
    --outdir runs/myrun --input-label "<label>"
# inspect
cat runs/myrun/figure-report.md
cat runs/myrun/fig/figure-captions.md
```

Single phases:

```bash
pixi run preflight ...   # no figures
pixi run maps ...        # Rscript bin/plot_map_leaflet.R ...
pixi run profiles ...    # Rscript bin/plot_profiles.R ...
pixi run report ...      # Rscript bin/build_report.R ...
```

Each phase appends to the append-only ledger `work/figure_status.jsonl` (the leaflet map worker no longer saves a ggplot snapshot; profile figures still save `work/plots/*.rds` for the fig 06 patchwork). If the ledger is missing when `report/` runs, the sub-skill refuses and points you back to phase 2/3.

## Realm matrix (SCOPE-banner compliance)

| Behavior | Marine | Freshwater | Terrestrial |
|---|---|---|---|
| Occurrence map + facets | ✅ | ✅ | ✅ |
| Profile figure | depth (`depth_m`…) | elevation/bioclim | elevation/bioclim |
| Env envelope | Bio-ORACLE (`env_bio_*`) | WorldClim/CHELSA (`env_wc_*`) | WorldClim/CHELSA (+ SoilGrids later) |
| Trait space | FishBase cols when present | FishBase cols (finfish) | typically absent → skipped |
| On-land records | visual sanity note | normal (note) | normal |

Mixed-realm projects run as separate runs per realm (dataset-level rule).

## Output contract

- **Map (fig 01):** interactive **single-file HTML** (self-contained leaflet, JS inlined) is the pinned map deliverable; a PNG snapshot is written via webshot2 + Chrome when a browser binary exists (ledger records the skip otherwise). No PDF for the map — a leaflet widget has no vector-PDF export.
- **Other figures:** PNG at **300 dpi** + vector **PDF** per figure (unchanged).
- The retired per-species facet figure (`02_species_maps`) and per-species static map files (`fig/per_species/`) are no longer produced — species detail lives in leaflet popups and layer toggles.
- `fig/figure-captions.md`: numbered, editable captions + per-figure file lists + records represented.
- `figure-report.md`: run header (input, realm, config) + rendered/skipped ledger.
- `work/` is scratch (git-ignored); `fig/` + `figure-report.md` are the bundle.

## Design invariants (do not break)

1. **One renderer**: R only (pinned). No Python renderer, no second plotting stack. Map = R leaflet; profile/envelope figures = R ggplot2.
2. **One plotting code path for all realms** — realm differences live in the config JSON.
3. **Graceful absence**: env/trait figures skip with a machine-readable reason; the leaflet map renders from the minimal contract. The PNG map snapshot additionally skips when no Chrome binary is present — the HTML is always produced.
4. **Reproducible subsampling**: geocurate pattern — `set.seed(42)`, cap `map.max_points`, record counts in captions.
5. **Offline basemap**: Natural Earth 1:50m land polygons embedded in the leaflet widget; the map must render on first open in any browser with **zero network access**. Remote tile providers are forbidden (OSM policy-blocks `file://` tile requests — user-observed; CARTO key-walls headless Chrome).
6. **Flags live upstream**: viz plots; it never computes or drops anything based on values.
7. **Sibling decoupling**: consumes §11.6-shaped files only; never imports edna-crosscheck / occurrence-publish code.
8. **SP-11 ring echo**: the map's ring comes only from the crosscheck run's R (`--near-km`); drawing a different radius must fail loudly, not silently drift.

## docs-corpus

Offline Markdown snapshots in `docs-corpus/` (fingerprinted in `docs-corpus/.fingerprints/sha256.txt`):
`ggplot2/`, `sf/`, `rnaturalearth/`, `arrow-r/`, `scico/`, `viridis/`. Read these before inventing function names/args.

## Self-update check

```bash
pixi run update-check
# UP-TO-DATE (0) / LOCAL-AHEAD (0) / BEHIND-BY-N (1) / OFFLINE (2) / NO-ORIGIN (2)
```

## Battle test

```bash
pixi run test-fixture     # (re)generate synthetic fixtures under test/
python3 test_smoke.py     # structural smoke tests
# full realm-matrix run:
pixi run viz --input test/test_fixture_marine.parquet --config config/run-config.marine.json --outdir runs/bt_marine --input-label "bt marine"
pixi run viz --input test/test_fixture_terrestrial.parquet --config config/run-config.terrestrial.json --outdir runs/bt_terr --input-label "bt terrestrial"
```

## Provenance

- Built with [skill-forge](https://github.com/cheahhl814/skill-forge), PLAN-marine-edna-meta-skill.md Phase 2 spec.
- Point-subsampling + basemap fallback pattern reused from the workspace `AMPLICON/bin/geocurate_inventory.R` experience (pinned).
- Sibling skills: `edna-crosscheck` (Phase 1, file contract §11.2) and `occurrence-publish` (Phase 3) — file-contract only, no code coupling.
