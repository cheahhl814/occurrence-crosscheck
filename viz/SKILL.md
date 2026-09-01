---
name: occurrence-viz
description: "PHASE 2 of the marine-eDNA meta-skill stack (PLAN-marine-edna-meta-skill.md §5): standalone, realm-aware publication-quality visualization of DwC-shaped occurrence tables — species occurrence maps (rnaturalearth + geocurate fallback pattern with fixed-seed point subsampling), realm-routed environmental profiles (marine → depth profiles; freshwater/terrestrial → elevation/bioclim profiles via the SAME plotting code with the x-axis variable from run config), per-species env envelopes, and optional trait-space plots, closed by a multi-panel report + auto-generated figure captions manifest. Renderer PINNED to R (ggplot2 + sf + rnaturalearth; arrow for parquet). Input contract §11.6: standalone — minimal DwC columns (scientificName, decimalLatitude, decimalLongitude, eventDate) required; env/trait columns optional and gracefully absent. Works on plain obis-gbif-fetch parquet, not just edna-crosscheck output. Visualizes observations, never flags — flagging lives in edna-crosscheck. Use when the user asks to 'plot occurrence data', 'map gbif/obis records', 'make depth/elevation profiles for eDNA species', 'env envelope plot', or 'publication figures from enriched.parquet'."
version: 1.0.0
updated: "2026-08-31"
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
  - "R packages: ggplot2, sf, rnaturalearth(+data), maps, arrow, scico, viridis, patchwork, scales, optparse, dplyr, tidyr, readr, jsonlite"
  - "no network access — fully local, no API calls, no tile servers"
---

# Skill: occurrence-viz

> **v1.0.0.** Realm-aware, standalone publication-quality occurrence visualization. This file is a **router** — the sub-skills do the work. Built with the bioinfo-skill-creator meta-skill per the BettaMt / AiX-BIO convention (preflight → build → debug → battle-test evidence chain; explicit ask-user stop points; signature libraries; docs-corpus).

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

## Pipeline — 4 sub-skills (phase detection: state of the run's `outdir/`)

| # | Phase | Goal | Sub-skill | Outputs |
|---|---|---|---|---|
| 1 | Preflight | Validate input + config; run summary; figure-set feasibility | `preflight/input-preflight/SKILL.md` | preflight summary + `work/figure_status.jsonl` |
| 2 | Maps | Occurrence map + per-species small multiples | `maps/occurrence-maps/SKILL.md` | `fig/01_*`, `fig/02_*` |
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
pixi run maps ...        # Rscript bin/plot_map.R ...
pixi run profiles ...    # Rscript bin/plot_profiles.R ...
pixi run report ...      # Rscript bin/build_report.R ...
```

Each phase appends to the append-only ledger `work/figure_status.jsonl` and saves its ggplot snapshot to `work/plots/*.rds`. If the ledger is missing when `report/` runs, the sub-skill refuses and points you back to phase 2/3.

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

- PNG at **300 dpi** + vector **PDF** per figure (pinned baseline). SVG optional in `output_formats` (needs `svglite`).
- `fig/figure-captions.md`: numbered, editable captions + per-figure file lists + records represented.
- `figure-report.md`: run header (input, realm, config) + rendered/skipped ledger.
- `work/` is scratch (git-ignored); `fig/` + `figure-report.md` are the bundle.

## Design invariants (do not break)

1. **One renderer**: R only (pinned). No Python renderer, no second plotting stack.
2. **One plotting code path for all realms** — realm differences live in the config JSON.
3. **Graceful absence**: env/trait figures skip with a machine-readable reason; maps always render from the minimal contract.
4. **Reproducible subsampling**: geocurate pattern — `set.seed(42)`, cap `map.max_points`, record counts in captions.
5. **Basemap fallback chain**: rnaturalearth (media, rnaturalearthdata) → `maps::map("world")` → bare frame; never hard-fail on a missing basemap dataset.
6. **Flags live upstream**: viz plots; it never computes or drops anything based on values.
7. **Sibling decoupling**: consumes §11.6-shaped files only; never imports edna-crosscheck / occurrence-publish code.

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
pixi run test-fixture          # (re)generate synthetic fixtures under test/
pixi run battle-test           # structural smoke tests (python3 test_smoke.py)
# full realm-matrix run:
pixi run viz --input test/test_fixture_marine.parquet --config config/run-config.marine.json --outdir runs/bt_marine --input-label "bt marine"
pixi run viz --input test/test_fixture_terrestrial.parquet --config config/run-config.terrestrial.json --outdir runs/bt_terr --input-label "bt terrestrial"
```

## Provenance

- Built with [bioinfo-skill-creator](https://github.com/cheahhl814/bioinfo-skill-creator) (v1.1.0), PLAN-marine-edna-meta-skill.md Phase 2 spec.
- Point-subsampling + basemap fallback pattern reused from the workspace `AMPLICON/bin/geocurate_inventory.R` experience (pinned).
- Sibling skills: `edna-crosscheck` (Phase 1, file contract §11.2) and `occurrence-publish` (Phase 3) — file-contract only, no code coupling.
## v1.4.0 — citable species images (`--images`)

`pixi run -e default -- Rscript bin/viz_run.R --input F.parquet --config config/<realm>.json --outdir OUT --per-species --near-km 150 --buffer-km 2000 --params <params.json> --counts <occurrence_counts.json> --images <work_dir>/species_images.csv`

Two additions consume the crosscheck `species_images.csv` manifest (PLAN §11.9):

- **fig 07_species_contact_sheet** (`bin/plot_contact_sheet.R`): one tile per species — cached
  photo + credit + SPDX license, colour-coded by flag; flagged/no-image taxa render as explicit
  placeholder tiles (flags never silently drop). Caption entry auto-appended by build_report.
- **per-species map thumbnails** (`plot_per_species.R --images`): photo inset top-right + credit
  line in the figure caption ("Photo: <creator> (<license>) via <source>").

Licence policy: cc-best (CC0/CC-BY(-SA)) preferred; by-nc allowed for internal reports;
all-rights-reserved and unlicensed images are excluded from embeds in the fetcher upstream.
Standalone workers: `pixi run -e default -- Rscript bin/plot_contact_sheet.R --images <csv> --outdir <out>`.

## v1.5.0 — genus-candidate panels + fig 08 (quarantined candidate layer)

For genus-only ASV groups (crosscheck genus-narrow), viz can render PREDICTED
species panels — quarantined by design: they never enter the species verdict
layer (no CONCORDANT/DISCORDANT words, no ledger verdict counts, separate
`species_maps/genus_candidates/` directory).

- `pixi run -e default -- Rscript bin/viz_run.R ... --genus-candidates <genus_candidates.csv> --candidates-context <candidates_context_occurrences.csv>`
  runs the `genuscandidates` phase (`bin/plot_genus_candidates.R`): per candidate
  (top-N, default 3 per genus) a panel map with a HOLLOW detection diamond and a
  plausibility label **SUPPORTED** (nearest record <= --near-km) / **WEAK**
  (in-region but distant) / **NO_RECORD** (zero records — absence of evidence).
  Requires `--candidates-context` (fetched upstream by
  `context_records.py --candidates <genus_candidates.csv>`): without the
  candidates' OWN context records every candidate would falsely read NO_RECORD
  (the detected-taxa context file only covers detected species).
- `--candidate-images <candidate_images.csv>` renders fig
  **08_genus_candidates_sheet** (bin/plot_contact_sheet.R): photos labelled
  "candidate of <genus>, rank n" — hypotheses for the review queue, NOT species
  identifications.

## v1.6.0 — habitat + IUCN annotations (`--habitat`)

`--habitat <habitat_iucn.csv>` (crosscheck habitat-iucn, PLAN §11.11) annotates every view:
- **per-species maps + candidate panels**: second subtitle line "habitat marine / brackish · IUCN Least Concern"
- **fig 07 + 08 contact sheets**: IUCN-colour-coded status line per tile (LC #1a7a3a -> CR #8e2a2a; NE/DD grey),
  bolded above the license line
Helpers live in bin/lib_viz.R (`habitat_iucn_note`, `iucn_col_for`, `IUCN_TILE_COL`).

## v1.7.0 — self-contained HTML report (`report-html` phase)

`pixi run report-html --params <params.json> --counts <occurrence_counts.json> --habitat <habitat_iucn.csv> \
  --species-images <csv> --candidate-images <csv> --candidates <genus_candidates.csv> \
  --context <context_occurrences.csv> --candidates-context <candidates_context_occurrences.csv> \
  --species-maps <dir> --candidate-panels <dir> --figures <dir> --images-dir <dir> \
  --out <report_dir> [--near-km 150] [--max-candidates 3] [--species-limit N --candidates-limit N (smoke)]`

- Generator: bin/build_report_html.py (python + jinja2, stdlib otherwise) + templates/report.html.j2;
  plotly.min.js vendored in vendor/ and COPIED into <out>/vendor/ so the report folder is portable
- Four tabs: Overview (KPIs, SVG verdict/IUCN/habitat charts, plotly scattergeo occurrence map with
  buffer ring + detection site, contact-sheet thumbnails), Species (filterable cards: verdict badge, map
  + photo lightbox, habitat + IUCN, per-image CC attribution), Genus Candidates (QUARANTINE: amber dashed
  cards, repeated GENUS-LEVEL HYPOTHESIS banner, SUPPORTED/WEAK/NO_RECORD filters), Methods
- Fully offline: no CDN, no runtime fetch (inline REPORT_DATA JSON); deep links #species/#candidates work
- Hard cross-checks (exit 2 on mismatch): generator-computed verdict/plausibility MUST equal the map/panel
  filename suffixes — wrong verdicts are never rendered; also fails on ambiguous/stale duplicate panels
- Candidate context = candidates-context + detected backdrop MERGED (binomial-key join), mirroring
  plot_genus_candidates.R exactly (the candidates-only fetch is GBIF-only + 100-row-capped)
- Outputs report/index.html (~850 KB) + vendor/plotly.min.js; PNG assets referenced relatively, never copied

## v1.8.0 — merged-ring maps + HTML report v2.0.0 (six tabs)

Merged-ring rendering (PLAN §11.13): per-species maps and candidate panels draw the dashed ring at
--near-km (the concordance threshold, NOT the fetch buffer); occurrences within the ring are solid,
beyond-ring records are pale/hollow and the map horizon extends to include the nearest beyond-ring
records, so a DISCORDANT taxon visibly shows "it occurs, but over THERE". Subtitles read
"X GBIF · Y OBIS within the R km ring · beyond: ... · nearest known record N km". NO_RECORD now means
absent from GBIF/OBIS globally (world counts), never "absent merely near the site".

HTML report v2.0.0: Overview drops the map/figures (KPIs, SVG charts, verdict table only); Species and
Genus Candidates each SPLIT into an images tab and a maps tab (six tabs total, all deep-linkable);
2-column grids with larger fonts; binary light/dark theme toggle (localStorage-persisted, honors
prefers-color-scheme by default); plotly scattergeo (in-ring solid / beyond-ring pale, ring at ring_km)
moved to the top of the Species Maps tab. 2024K1: 48 species (18/27/3 — unchanged), candidates now
45 SUPPORTED / 1 WEAK (fuller OBIS context after refetch; Alepes vari genuinely 39 km — the old
GBIF-only capped candidates fetch had missed it).

## v1.8.1 — map inset removal + overview chart polish (report v2.0.1)

- plot_per_species.R: the citable-photo inset (top-right rasterGrob) is REMOVED from map images —
  redundant with the report's Species images tab and it covered map regions. `--images` is still
  accepted (viz_run compatibility) but ignored; photos + attribution live on in the report cards and
  fig 07 contact sheet (unchanged).
- Report Overview: all four chart cards (Species verdicts, Candidate plausibility, IUCN, Habitat mix)
  now render responsive SVGs (viewBox + width:100%, larger canvases: donut 240px, bars 460px) so the
  cards fill their 2-column width — no more dead space at the right.
- IUCN bar chart: per-category colours in severity order (EX/EW dark -> CR #8e2a2a -> EN orange ->
  VU yellow -> NT lime -> LC green -> DD grey -> NE light grey), keyed by full category name AND code.

