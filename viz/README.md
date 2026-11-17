# occurrence-viz

**v1.9.1.** Standalone, realm-aware publication-quality occurrence visualization for eDNA / biodiversity data: one interactive occurrence map (R leaflet, self-contained HTML), depth/elevation profiles, env envelopes, trait space, multi-panel reports — any DwC-shaped parquet/CSV.

This is the **occurrence-viz** skill (Phase 2 of the [marine-eDNA meta-skill stack](../../../PLAN-marine-edna-meta-skill.md)), built with the [skill-forge](https://github.com/cheahhl814/skill-forge) meta-skill.

## Contents

- [🚀 Installation](#-installation)
- [💡 Usage](#-usage)
- [🔬 Pipeline overview](#-pipeline-overview)
- [🧰 Tools](#-tools)
- [🔄 Update check](#-update-check)
- [📁 Repository layout](#-repository-layout)
- [🔒 Hard guarantees](#-hard-guarantees)
- [Provenance](#provenance)

## 🚀 Installation

```bash
git clone https://github.com/cheahhl814/occurrence-crosscheck.git   # this skill lives in viz/
cd occurrence-crosscheck/viz
pixi install                                    # R 4.3+ env from this pixi.toml
```

## 💡 Usage

```bash
pixi run viz \
    --input test/test_fixture_marine.parquet \
    --config config/run-config.marine.json \
    --outdir runs/demo_marine --input-label "demo marine"
cat runs/demo_marine/figure-report.md
```

Single phases: `pixi run preflight|maps|profiles|report` (same `--input --config --outdir` arguments). Real OBIS/GBIF pulls drop straight in:

```bash
pixi run viz --input ~/data/obis_pull.parquet --config config/run-config.marine.json --outdir runs/obis_pull
```

What you get:

| Input | Realm config | Figures out |
|---|---|---|
| Any table with `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate` (parquet/csv/tsv) | `marine` \| `freshwater` \| `terrestrial` (JSON) | one interactive occurrence map (leaflet HTML + best-effort PNG snapshot), realm-routed env profile, per-species env envelope, optional trait space, multi-panel overview, captions manifest |

- **Standalone** (PLAN §11.6): works on a plain `obis-gbif-fetch` parquet — env/trait plots render only when their columns exist, skipped with a logged reason otherwise.
- **Realm-aware by config, not code**: marine → depth profiles; freshwater/terrestrial → elevation/bioclim profiles. Same plotting code, different x-axis variable from the run config.
- **Renderer pinned to R** — leaflet for the map, ggplot2 for profiles/envelopes; `arrow` reads parquet. One toolchain, no Python renderer.
- **Never flags** — viz draws observations; `edna-crosscheck` computes the flags.

Realm matrix (x-axis resolution order — first present wins):

| | Marine | Freshwater | Terrestrial |
|---|---|---|---|
| Profile x-axis | `depth_m` / `depth` / `env_bio_depth_m` | `elev` / `env_wc_elev` / `trait_depth_min_m` | `elev` / `env_wc_elev` / `env_wc_bio1` |
| Envelope variables | `env_bio_temp_ss`, `env_bio_salinity_ss` | `env_wc_bio1`, `env_wc_bio12` | `env_wc_bio1`, `env_wc_bio12` |

Copy a config and edit — that's the realm switch. There is no `--realm` flag on purpose: realm differences live in config, not code.

Outputs: `fig/01_occurrence_map.html` (pinned deliverable; a PNG snapshot is best-effort via webshot2 + Chrome) · `fig/03..08_*.png|pdf` per figure · `fig/figure-captions.md` — auto-generated caption manifest (edit before publication) · `figure-report.md` — rendered vs skipped figures.

## 🔬 Pipeline overview

| # | Phase | Sub-skill | Artifact |
|---|---|---|---|
| 1 | Preflight | [preflight/input-preflight](preflight/input-preflight/SKILL.md) | run summary + `work/figure_status.jsonl` |
| 2 | Maps | [maps/occurrence-maps](maps/occurrence-maps/SKILL.md) | `fig/01_occurrence_map.html` (+ `.png` snapshot) |
| 3 | Profiles | [profiles-env/env-profiles](profiles-env/env-profiles/SKILL.md) | `fig/03_env_profile.*`, `fig/04_env_envelope.*`, `fig/05_trait_space.*` |
| 4 | Report | [report/figure-report](report/figure-report/SKILL.md) | `fig/06_multispecies_overview.*`, `fig/figure-captions.md`, `figure-report.md` |

## 🧰 Tools

- R 4.3+ via pixi (conda-forge): `leaflet` + `htmlwidgets` + `webshot2` (map + PNG snapshot), `ggplot2`/`sf`/`patchwork`/`scico`/`viridis` (profile/envelope figures), `arrow` (parquet), `rnaturalearth` (coastlines for non-map figures).
- Offline docs snapshots in `docs-corpus/` (fingerprinted): `ggplot2/`, `sf/`, `rnaturalearth/`, `arrow-r/`, `scico/`, `viridis/`.
- Basemap: **embedded Natural Earth 1:50m land polygons** inside the leaflet widget — the map renders with zero network access (remote tile providers are forbidden; see `SKILL.md` §Design invariants).

## 🔄 Update check

Every skill ships a self-update check comparing the deployed git SHA against upstream via `git fetch` (no API calls, no extra dependencies):

```bash
pixi run update-check
# UP-TO-DATE (0) / LOCAL-AHEAD (0) / BEHIND-BY-N (1) / OFFLINE (2) / NO-ORIGIN (2)
```

When `BEHIND-BY-N`, re-sync this directory from the upstream `occurrence-crosscheck` repository (the skill lives in `viz/`), then verify with `diff -rq`.

## 📁 Repository layout

```
viz/
├── SKILL.md                            # Master orchestrator (router only)
├── README.md                           # This file
├── pixi.toml                           # Pixi env: R + leaflet/ggplot2/sf/arrow/...
├── preflight/input-preflight/          # Phase 1 — input + config validation
├── maps/occurrence-maps/               # Phase 2 — interactive occurrence map
├── profiles-env/env-profiles/          # Phase 3 — realm-routed profiles + envelopes
├── report/figure-report/               # Phase 4 — multi-panel + captions manifest
├── bin/                                # viz_run.R orchestrator + phase workers + lib_viz.R
├── config/                             # run-config.{marine,freshwater,terrestrial}.json
├── docs-corpus/                        # offline docs snapshots (fingerprinted)
├── templates/                          # run-config template
├── test/                               # fixtures + fixture generator
├── bin/skill-update-check.py           # self-update check (pixi run update-check)
└── test_smoke.py                       # structural smoke tests
```

## 🔒 Hard guarantees

- **Never flags** — viz plots observations; it never computes, and never drops, on flag values.
- **Zero-network map** — the leaflet widget renders fully offline (embedded Natural Earth basemap); no tile servers, ever.
- **Graceful absence** — missing env/trait columns skip those figures with a machine-readable reason, never an error.
- **Realm in config, never in code** — no `if (realm == …)` in plotting code; the run config picks the x-axis and figure family.
- **One renderer per figure family** — leaflet for the map, ggplot2 for profiles/envelopes; no second stack.

## Provenance

Built with the [skill-forge](https://github.com/cheahhl814/skill-forge) meta-skill. Pattern adopted from:

- **BettaMt-agents** — https://github.com/cheahhl814/BettaMt-agents
- **bacterial-genome-analysis** — https://github.com/cheahhl814/bacterial-genome-analysis
- **AMPLICON `bin/geocurate_inventory.R`** — point-subsampling (seed 42) + basemap fallback chain (pinned reuse)

Note: no `battle-test-report.md` is committed for this sub-skill yet — the November map-renderer rework post-dates the last battle-test. See `SKILL.md` for smoke tests (`python3 test_smoke.py`).
