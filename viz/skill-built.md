# Skill build report — occurrence-viz

Generated: 2026-08-31
Builder:   bioinfo-skill-creator v1.1.0 `build/skill-builder` phase (agent-executed)
Inputs:    `preflight.md` (verdict GO) + `params.json` (16 tools, all `found`)

## Build summary

- Renderer PINNED and shipped: **R only** (ggplot2 + sf + rnaturalearth/data + maps; arrow for parquet). No Python renderer, no second plotting stack.
- Skill shape: `multi-tool-pipeline`, **bash-only** (no nextflow runner, per PLAN §3 + pinned decision).
- Realm-awareness: run-config JSON only (`config/run-config.{marine,freshwater,terrestrial}.json`) — verified by smoke test `test_18_no_per_call_realm_branching_in_workers` (no `cfg$realm ==` / realm literal branching in any bin/*.R worker).
- Sub-skills: the PLAN §5 pinned set — `preflight/input-preflight/`, `maps/occurrence-maps/`, `profiles-env/env-profiles/`, `report/figure-report/` — each with ≥3 ask-user stop points and ≥3 signature-library entries (smoke-enforced).
- Input contract: PLAN §11.6 standalone (minimal DwC) — enforced in `bin/lib_viz.R::validate_dwctable()`.
- Nextflow runner: **not** scaffolded (pinned). Lite tree: not scaffolded (`target_tiers: ["large"]`).
- docs-corpus: 6 packages, 8 files, sha256-fingerprinted in `docs-corpus/.fingerprints/sha256.txt`.
- Debug loop executed once (verdict RECOVERABLE, 8 defects fixed — see `debug-report.md`).

## File inventory (sha256)

| File | Size | sha256 (first 12) |
|---|---|---|
| SKILL.md | 8.6K | (see `git log`-pinned commit) |
| README.md | 6.1K | — |
| pixi.toml | 1.5K | `pixi lock --dry-run` clean |
| .gitignore | 0.2K | — |
| bin/lib_viz.R | 9.8K | shared helpers (§11.6 validation, subsample seed-42, coastline fallback, PROJ_DATA init, palettes, save_fig, ledger) |
| bin/viz_run.R | 5.5K | orchestrator driver + run-preflight summary |
| bin/plot_map.R | 7.0K | maps worker (fig 01/02) |
| bin/plot_profiles.R | 10.4K | profiles worker (fig 03/04/05) |
| bin/build_report.R | 9.7K | report worker (fig 06 + captions manifest + report) |
| bin/skill-update-check.py | 6.4K | rendered from meta-skill template; py_compile OK |
| config/run-config.marine.json | 0.9K | realm marine (depth profiles) |
| config/run-config.freshwater.json | 1.0K | realm freshwater (elev/bioclim) |
| config/run-config.terrestrial.json | 1.0K | realm terrestrial (elev/bioclim) |
| templates/run-config.template.json | 1.0K | blank config template |
| preflight/input-preflight/SKILL.md | 5.6K | SP1–SP5 + 6-row signature library |
| maps/occurrence-maps/SKILL.md | 4.9K | SP1–SP4 + 7-row signature library |
| profiles-env/env-profiles/SKILL.md | 5.2K | SP1–SP4 + 6-row signature library |
| report/figure-report/SKILL.md | 4.5K | SP1–SP3 + 6-row signature library |
| docs-corpus/{ggplot2,sf,rnaturalearth,arrow-r,scico,viridis}/* | 32K | 8 md files + fingerprints |
| test/make_test_fixture.R | 5.1K | synthetic fixture generator (marine/terrestrial/minimal) |
| test/test_fixture_{marine,terrestrial,minimal,real_obis}.parquet | 116K | fixtures (real_obis = 500 live OBIS records) |
| test_smoke.py | 10K | 22 structural checks |

(exact sha256s are captured by git; the build sub-skill records them in the first commit rather than inlining here.)

## Environment

- pixi 0.70.1; env = conda-forge: r-base 4.5.x (+ 15 R packages), proj 9.8.1, geos, libgdal.
- Known env quirk (self-healed by `bin/lib_viz.R::proj_data_init`): conda-forge proj ≥9 ships no conda activate scripts → `PROJ_DATA` unset → sf/geom_sf fails with `crs not found: is it missing?`. The lib resolves the env prefix from the sf install path and sets PROJ_DATA/PROJ_LIB at load.

## Readiness for Phase 4

skill-built ✅ — hand off to battle-test (structural + execution); verdict in `battle-test-report.md`.