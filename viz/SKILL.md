---
name: occurrence-viz
description: "PHASE 2 of the marine-eDNA meta-skill stack (PLAN-marine-edna-meta-skill.md §5): standalone, realm-aware visualization of DwC-shaped occurrence tables — ONE interactive species occurrence map (R leaflet, self-contained single-file HTML; v1.9.0 replaces the retired rnaturalearth/ggplot2 static maps), realm-routed environmental profiles, per-species env envelopes, and optional trait-space plots, closed by a multi-panel report + auto-generated figure captions manifest. Input contract §11.6: standalone — minimal DwC columns (scientificName, decimalLatitude, decimalLongitude, eventDate) required; env/trait columns optional and gracefully absent. Works on plain obis-gbif-fetch parquet, not just edna-crosscheck output. Visualizes observations, never flags — flagging lives in edna-crosscheck. Use when the user asks to 'plot occurrence data', 'map gbif/obis records', 'make depth/elevation profiles for eDNA species', 'env envelope plot', or 'publication figures from enriched.parquet'."
version: 1.9.0
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
  - "R packages: ggplot2, sf, rnaturalearth(+data), maps, arrow, scico, viridis, patchwork, scales, optparse, dplyr, tidyr, readr, jsonlite"
  - "no network access — fully local, no API calls, no tile servers"
disable-model-invocation: true
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

- **Map (fig 01, v1.9.0):** interactive **single-file HTML** (self-contained leaflet, JS inlined) is the pinned map deliverable; a PNG snapshot is written via webshot2 + Chrome when a browser binary exists (ledger records the skip otherwise). No PDF for the map — a leaflet widget has no vector-PDF export.
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
5. **Offline basemap**: Natural Earth 1:50m land polygons embedded in the leaflet widget; the map must render on first open in any browser with **zero network access**. Remote tile providers are forbidden (OSM policy-blocks `file://` tile requests — user-observed 2026-11-11; CARTO key-walls headless Chrome).
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
## v1.9.0 (2026-11-11) — map renderer swap: R leaflet replaces ALL ggplot2 maps

Motivated by the Ryan-12S battle test (2026-11-11, executor + Claude Code inspection): the static
maps never drew the concordance ring, used a non-discriminable 57-hue legend, overlapped
title/legend, and collapsed 60 coincident points into one dot.

- **Retired + deleted:** `bin/plot_map.R`, `bin/plot_per_species.R`,
  `bin/plot_genus_candidates.R` (rnaturalearth/ggplot2 static maps).
- **New:** `bin/plot_map_leaflet.R` — one interactive R-leaflet map
  (`maps/occurrence-maps/SKILL.md` v2.0.0): concordance ring (SP-11 echo), verdict layer
  toggles, per-species ring-vs-world counts in popups, optional context overlay, keyless OSM
  basemap, self-contained single-file HTML + best-effort PNG snapshot (webshot2 + Chrome).
- **pixi deps:** + r-leaflet, r-htmlwidgets, r-webshot2.
- **v1.9.1 basemap hardening:** remote tiles removed entirely after OSM policy-blocked the
  user's browser on the battle-test HTML — the basemap is now embedded Natural Earth 1:50m
  land polygons with a CSS ocean colour (3.8 MB self-contained HTML, verified zero external
  requests).
- **fig06 multispecies overview:** needs ≥2 ggplot panels; with the map gone it typically
  skips (profiles alone) — the interactive map replaces its overview role.
- **build_report_html.py `--species-maps` / `--candidate-panels`:** the upstream R producers
  are gone; those cross-check image columns are retired. Not rewritten (legacy genus-narrow
  feature); the report still renders from its own context CSVs.
- **Contact sheet (fig 07, `--images`) kept** — it is an image grid, not a map. The v1.4.0
  per-species map thumbnails and the v1.5.0 ggplot candidate-panel maps are retired with the
  deleted renderers.

## v1.4.0 — citable species images (`--images`) — contact sheet retained; map thumbnails retired in v1.9.0

`pixi run -e default -- Rscript bin/viz_run.R --input F.parquet --config config/<realm>.json --outdir OUT --params <params.json> --counts <occurrence_counts.json> --images <work_dir>/species_images.csv`

One addition consumes the crosscheck `species_images.csv` manifest (PLAN §11.9):

- **fig 07_species_contact_sheet** (`bin/plot_contact_sheet.R`): one tile per species — cached
  photo + credit + SPDX license, colour-coded by flag; flagged/no-image taxa render as explicit
  placeholder tiles (flags never silently drop). Caption entry auto-appended by build_report.
- ~~per-species map thumbnails~~ — retired with the ggplot2 map removal (v1.9.0).

Licence policy: cc-best (CC0/CC-BY(-SA)) preferred; by-nc allowed for internal reports;
all-rights-reserved and unlicensed images are excluded from embeds in the fetcher upstream.
Standalone workers: `pixi run -e default -- Rscript bin/plot_contact_sheet.R --images <csv> --outdir <out>`.

## v1.5.0 — ~~genus-candidate panels~~ RETIRED in v1.9.0; candidate contact sheet (fig 08) kept

The ggplot2 candidate-panel maps (`bin/plot_genus_candidates.R`, the `genuscandidates`
phase and `--genus-candidates` / `--candidates-context` flags) are **deleted** with the v1.8.0
renderer swap. Genus-narrow candidates still flow through crosscheck's `genus_narrow.py` and
can be surfaced as imagery only via the quarantined contact sheet:

- `--candidate-images <candidate_images.csv>` renders fig **08_genus_candidates_sheet**
  (bin/plot_contact_sheet.R): photos labelled "candidate of <genus>, rank n" — hypotheses for
  the review queue, NOT species identifications.

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
- Report v2.0.2: the plotly occurrence-map container is aspect-fitted to the geo frame
  (lon-span × cos(midLat) / lat-span, clamped 0.75–2.0) and centered with a max-width cap —
  the map fills its container instead of leaving a huge dead band on the right of the wide card.

## v1.0.1 — runtime ask-user stop points (§0.5)

Added a "0.5 Ask-User Stop Points (runtime parameters)" section: SP-11 echoes crosscheck's
concordance-ring pin (confirm-not-choose, since the report generator hard-fails exit 2 on a
ring mismatch), SP-15 covers the `context_records` context-fetch budget, and SP-16 covers
genus-narrow candidate cutoffs. Each carries an explicit auto-pick condition.

## v1.0.3 — occurrence-map legend (colour → species mapping was unreadable)

Production finding (Chiloscyllium GBIF+OBIS run, Indo-West Pacific): `fig/01_occurrence_map.png`
colours points by species but the overview plot suppressed its legend
(`theme(legend.position = "none")`), leaving no indication of which colour is which species.
The per-species small multiples (fig 02) and `per_species/` files carry panel titles and need no
legend — the fix targets the all-species overview only.

- `bin/plot_map.R` (fig 01): legend now rendered on the right, with bold "Species" title and
  italic species keys (matches the italic-label convention of fig 02 strips and the iTOL route).
- Fig 02 small multiples, `per_species/` files, and the fig 06 patchwork are unchanged — each is
  self-labelled by design.
- Captions manifest unchanged (`figure-captions.md` picks up counts as before).

## v1.0.2 — production-run findings: antimeridian crop bug, title bleed, per-species map files

Three issues found running against real *Chiloscyllium* GBIF+OBIS data (Indo-West Pacific, wide
longitude span) — see `HANDOFF-viz-issues-2026-09.md` for full repro:

- **Coastline crop bug (HIGH):** `sf::st_crop()`/`st_intersection()` (sf 1.1.2) silently drop
  most/all continental polygons when the crop bbox's longitude span exceeds 180° — they misread
  the box as antimeridian-crossing and keep only the complementary sliver, with no error raised.
  `lib_viz.R` gains `safe_crop_coast()`: selects intersecting features with `st_intersects()`
  (predicate-only, unaffected by the bug) and skips the buggy clip entirely for spans > 180°,
  returning the unclipped intersecting features instead of silently losing them. Used by
  `plot_map.R` (fig 01/02/per-species) and `plot_per_species.R` (concordance-ring maps).
- **Title/subtitle bleed (MEDIUM):** long `--input-label` values overflowed `plot.title`/
  `plot.subtitle` off the right edge of fixed-width panels (worst in the fig 06 patchwork combo).
  `lib_viz.R` gains `wrap_title()` (base `strwrap`, no new dependency); applied to all figure
  titles/subtitles in `plot_map.R` and `plot_profiles.R`.
- **Per-species map files (MEDIUM, requested):** `plot_map.R` now writes one map file per species
  to `fig/per_species/{sanitized_scientificName}.{png,pdf}` in addition to the existing combined
  fig 02 small-multiples panel (kept by default for backwards compatibility). Opt out via
  `map.per_species_files: false` in the run config. Each file is registered in the figure-status
  ledger and picked up by `fig/figure-captions.md` via a generic per-species caption.
- Minor, same area: fig 02's caption now reports the real species/point counts (was a bare
  "small multiples" sentence); `build_report.R` had a stray copy-pasted caption fragment bleeding
  a rogue sentence into `figure-report.md` and was missing the `08_genus_candidates_sheet` case
  from the actual captions switch — both fixed.

