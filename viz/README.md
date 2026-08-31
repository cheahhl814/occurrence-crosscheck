# occurrence-viz

> **v1.0.0.** Standalone, realm-aware publication-quality occurrence visualization for eDNA / biodiversity data: maps, depth/elevation profiles, env envelopes, trait space, multi-panel reports — any DwC-shaped parquet/CSV.

This is the **occurrence-viz** skill (Phase 2 of the [marine-eDNA meta-skill stack](../../../PLAN-marine-edna-meta-skill.md)), built with the [bioinfo-skill-creator](https://github.com/cheahhl814/bioinfo-skill-creator) meta-skill.

## What it does

| Input | Realm config | Figures out |
|---|---|---|
| Any table with `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate` (parquet/csv/tsv) | `marine` \| `freshwater` \| `terrestrial` (JSON) | occurrence map, per-species facet maps, realm-routed env profile, per-species env envelope, optional trait space, multi-panel overview, captions manifest |

- **Standalone** (PLAN §11.6): works on a plain `obis-gbif-fetch` parquet — env/trait plots render only when their columns exist, skipped with a logged reason otherwise.
- **Realm-aware by config, not code**: marine → depth profiles; freshwater/terrestrial → elevation/bioclim profiles. Same plotting code, different x-axis variable from the run config.
- **Renderer pinned to R** — ggplot2 + sf + rnaturalearth (+ `maps` fallback); `arrow` reads parquet. One renderer, no Python.
- **Never flags** — viz draws observations; `edna-crosscheck` computes the flags.

## Pipeline (4 phases)

| # | Phase | Sub-skill | Artifact |
|---|---|---|---|
| 1 | Preflight | [preflight/input-preflight](preflight/input-preflight/SKILL.md) | run summary + `work/figure_status.jsonl` |
| 2 | Maps | [maps/occurrence-maps](maps/occurrence-maps/SKILL.md) | `fig/01_occurrence_map.*`, `fig/02_species_maps.*` |
| 3 | Profiles | [profiles-env/env-profiles](profiles-env/env-profiles/SKILL.md) | `fig/03_env_profile.*`, `fig/04_env_envelope.*`, `fig/05_trait_space.*` |
| 4 | Report | [report/figure-report](report/figure-report/SKILL.md) | `fig/06_multispecies_overview.*`, `fig/figure-captions.md`, `figure-report.md` |

## Quick start

```bash
pixi install                                    # R 4.3+ env from this pixi.toml
pixi run viz \
    --input test/test_fixture_marine.parquet \
    --config config/run-config.marine.json \
    --outdir runs/demo_marine --input-label "demo marine"
cat runs/demo_marine/figure-report.md
```

Single phases: `pixi run preflight|maps|profiles|report` (same `--input --config --outdir` arguments). Real OBIS/GBIF pulls from `workflows/obis-gbif-fetch` drop straight in:

```bash
pixi run viz --input ~/data/obis_pull.parquet --config config/run-config.marine.json --outdir runs/obis_pull
```

## Realm matrix

| | Marine | Freshwater | Terrestrial |
|---|---|---|---|
| Profile x-axis (first present wins) | `depth_m` / `depth` / `env_bio_depth_m` | `elev` / `env_wc_elev` / `trait_depth_min_m` | `elev` / `env_wc_elev` / `env_wc_bio1` |
| Envelope variables | `env_bio_temp_ss`, `env_bio_salinity_ss` | `env_wc_bio1`, `env_wc_bio12` | `env_wc_bio1`, `env_wc_bio12` |

Copy a config and edit — that's the realm switch. There is no `--realm` flag on purpose: realm differences live in config, not code.

## Outputs

- `300-dpi PNG + vector PDF` per figure (pinned); SVG optional (`svglite`).
- `fig/figure-captions.md` — auto-generated caption manifest (edit before publication).
- `figure-report.md` — rendered vs skipped figures (skips include reasons per PLAN §11.6 graceful absence).

## Battle test

```bash
pixi run test-fixture      # synthetic marine + terrestrial + minimal-DwC fixtures → test/
pixi run battle-test       # python3 test_smoke.py structural checks
# realm-matrix execution → runs/battletest_marine{,_terr}/ (see battle-test-report.md)
```

## Update Check

Every skill ships with a self-update check comparing the deployed git SHA against upstream `github.com/cheahhl814/occurrence-viz` via `git fetch` (no API calls, no extra dependencies):

```bash
pixi run update-check
# UP-TO-DATE (0) / LOCAL-AHEAD (0) / BEHIND-BY-N (1) / OFFLINE (2) / NO-ORIGIN (2)
```

When `BEHIND-BY-N`, re-deploy per AGENTS.md §4a:

```bash
rsync -a --exclude='.git' \
    ~/claude_workspace/bioinformatics/AIx-BIO/skills/occurrence-viz/ \
    ~/.pi/agent/skills/occurrence-viz/
diff -rq <src> <dst> --exclude='.git'   # verify zero drift
```

## Repository layout

```
occurrence-viz/
├── SKILL.md                            # Master orchestrator (router only)
├── README.md                           # This file
├── pixi.toml                           # Pixi env: R + ggplot2/sf/rnaturalearth/arrow/...
├── preflight/input-preflight/          # Phase 1 — input + config validation
├── maps/occurrence-maps/               # Phase 2 — occurrence maps
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

## Provenance

Built with the [bioinfo-skill-creator](https://github.com/cheahhl814/bioinfo-skill-creator) meta-skill. Pattern adopted from:

- **BettaMt-agents** — https://github.com/cheahhl814/BettaMt-agents
- **bacterial-genome-analysis** — https://github.com/cheahhl814/bacterial-genome-analysis
- **AMPLICON `bin/geocurate_inventory.R`** — point-subsampling (seed 42) + rnaturalearth→maps fallback chain (pinned reuse)

## License

Same as the rest of the AiX-BIO skill tree (private GitHub repo, MIT-style — see repository owner).