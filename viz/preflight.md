# Skill creator preflight report — `occurrence-viz`

Run:        /home/cheahhl814/claude_workspace/bioinformatics/AIx-BIO/skills/occurrence-viz
Generated:  2026-08-31T15:25:00+08:00
Meta-skill: bioinfo-skill-creator v1.1.0
Plan:       /home/cheahhl814/claude_workspace/bioinformatics/AIx-BIO/PLAN-marine-edna-meta-skill.md (read in full; not modified)

## Overall verdict

**GO** ✅

`occurrence-viz` (PLAN Phase 2) queued for build: R renderer (ggplot2 + sf + rnaturalearth, arrow for parquet), bash-only multi-tool pipeline, 4 workflow sub-skills, realm-aware via run config, PLAN §11.6 standalone input contract. Two sibling skills (edna-crosscheck, occurrence-publish) are being built in parallel — the only coupling is the documented file contract; no code imports.

## Pinned decisions (from task prompt — resolved WITHOUT ask-user blocking)

| # | Stop point | Pinned resolution |
|---|---|---|
| SP3/shape | Skill shape | `multi-tool-pipeline` — this is a plotting skill, NOT a meta-skill with runners. Bash-only, bash recipes are the execution path. |
| SP-nextflow | Nextflow runner | **No** — PLAN §3: I/O-bound, no Nextflow runner (`with_nextflow_runner: false`). |
| renderer | One renderer | **R** (ggplot2 + sf + rnaturalearth; `arrow` for parquet input). No Python renderer. |
| sub-skills | Granularity | `preflight/`, `maps/`, `profiles-env/`, `report/` per PLAN §5. |
| realm | Realm-awareness | Via run config / CLI argument (dataset-level), NOT per-call code branching. marine → depth profiles; freshwater/terrestrial → elevation/bioclim profiles; **same plotting code**, different x-axis variable from run config. |
| input | §11.6 contract | Standalone: minimal DwC columns `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate` required; env/trait columns optional — trait/env figures render only when their columns exist. Must plot a plain obis-gbif-fetch parquet, not just crosscheck output. |
| SP9 | Target tiers | `["large"]` (agents only; no lite tree requested). |
| SP5 | Git | `git init --initial-branch=master`; **local commits only, no push**; **no deploy to ~/.pi/agent/skills/**. |
| SP6 | Docs-corpus | REQUIRED for: ggplot2, sf, rnaturalearth, arrow (R), plus chosen palette packages (scico, viridis). |
| battle-test | Fixtures | Synthetic DwC parquet under `test/` — (a) marine realm: map + depth profile; (b) terrestrial realm: map + elevation/bioclim envelope; both 300 dpi PNG + PDF. Real OBIS/GBIF fetch optional if network allows; synthetic acceptable offline. |

## Evidence

| Check | Verdict | Value | Threshold |
|---|---|---|---|
| Skill name (kebab-case) | ✅ | `occurrence-viz` | valid regex |
| Skill name uniqueness | ✅ | RUN_DIR is the skill dir; no pre-existing different skill | unique |
| Target directory writable | ✅ | created + writable | writable |
| Tool inventory | ✅ | 16 R packages | ≥ 1 |
| Pixi env | ✅ | pixi 0.70.1 | installed |
| Tool availability (`pixi search` conda-forge) | ✅ | 15/16 found; `r-rnaturalearthhires` not packaged (not in inventory — optional layer) | all resolve |
| Git status | ✅ | initialized (`--initial-branch=master`), local only | initialized |
| Disk space | ✅ | 135 GB free | ≥ 5 GB |
| PLAN consistency | ✅ | §5 spec ↔ §2 architecture ↔ §11.6 contract coherent for this skill | consistent |
| Pattern reference found | ✅ | `/home/cheahhl814/claude_workspace/bioinformatics/AMPLICON/bin/geocurate_inventory.R` (point subsampling `map_points_max` cap with `set.seed(42)`; coastline fallback `rnaturalearth → maps::map() → bare frame`) | present |

## Recommendations

- **Renderer**: R, pixi-managed (`r-base` via conda-forge — known to work on this machine).
- **Sub-skills** (workflow): preflight, maps, profiles-env, report. Debug signature libraries live inside each sub-skill's `§Troubleshooting — Signature library` (≥ 3 entries each) rather than as a separate `debug/` dir — deviation note below.
- **Realm routing**: run config JSON (`config realm`, `x-axis variable`) consumed by plot scripts — no realm if-statements in plotting code.
- **Output formats**: 300-dpi PNG + PDF (ragg or grDevices); SVG optional at preflight of each run.

## Tools

| Tool | Role | `pixi search` status |
|---|---|---|
| r-base | runtime | ✅ found |
| r-ggplot2 | renderer | ✅ found |
| r-sf | spatial | ✅ found |
| r-rnaturalearth | basemap | ✅ found (after name correction) |
| r-rnaturalearthdata | basemap data (medium, 1:50m) | ✅ found (after name correction) |
| r-maps | basemap fallback | ✅ found |
| r-arrow | parquet IO | ✅ found |
| r-scico | palette (perceptually uniform) | ✅ found |
| r-viridis | palette (colour-blind safe) | ✅ found |
| r-patchwork | multi-panel assembly | ✅ found |
| r-scales | scale/legend formatting | ✅ found |
| r-optparse | CLI args | ✅ found |
| r-dplyr | wrangling | ✅ found |
| r-tidyr | wrangling | ✅ found |
| r-readr | CSV IO | ✅ found |
| r-jsonlite | run-config JSON IO | ✅ found |

## Docs-corpus plan (required sources)

| Tool | Corpus dir | Sources planned |
|---|---|---|
| ggplot2 | `docs-corpus/ggplot2/` | GitHub repo README/reference docs (docs-ingest strategy 3); tidyverse site fallback |
| sf | `docs-corpus/sf/` | GitHub r-spatial/sf README + vignette list |
| rnaturalearth | `docs-corpus/rnaturalearth/` | GitHub rspatial/rnaturalearth README |
| arrow (R) | `docs-corpus/arrow-r/` | arrow-r-nightly / apache arrow R docs |
| scico | `docs-corpus/scico/` | GitHub thomasp85/scico README |
| viridis | `docs-corpus/viridis/` | CRAN/sjmgarnier viridis README |

## Deviations from the meta-skill default (recorded, none blocking)

1. **Stop points resolved from pinned decisions, not ask-user** — per task rule §11.8.4; every pinned answer recorded in the table above.
2. **Sub-skill set** is the PLAN §5 workflow set (preflight / maps / profiles-env / report) — no separate `debug/` or `battle-test/` sub-skill directories in the shipped skill; failure-interpretation lives as signature libraries inside each workflow sub-skill, and construct-time debug/battle-test artifacts (`debug-report.md` if needed, `battle-test-report.md`) are written to RUN_DIR by this build session per bioinfo-skill-creator phases.
3. **`r-rnaturalearthhires` unavailable on conda-forge** — high-res basemap not shipped; medium (1:50m via rnaturalearthdata) is baseline with `maps::map()` fallback (geocurate pattern). A `--coastline` CLI flag preserves the fallback chain.
4. **Siblings not imported** — occurrence-viz consumes crosscheck output ONLY through the PLAN §11.2/§11.6 file contract; no shared code, no runners.

## Handoff

Verdict `GO` → hand off to **build/skill-builder** (this build session): render the skill tree, populate `docs-corpus/`, write `skill-built.md`.

## Reproducibility

- params.json:     skills/occurrence-viz/params.json
- evidence:        skills/occurrence-viz/preflight_evidence.txt
- this report:     skills/occurrence-viz/preflight.md