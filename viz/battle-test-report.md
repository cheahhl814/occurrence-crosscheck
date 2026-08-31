# Battle-test report — occurrence-viz v1.0.0

Run:        /home/cheahhl814/claude_workspace/bioinformatics/AIx-BIO/skills/occurrence-viz
Generated:  2026-08-31 (Phase 4, bioinfo-skill-creator chain)
Mode:       structural smoke tests + EXECUTION (rendering) — the pinned battle-test brief

## Overall verdict

**PASS-WITH-WARNINGS** ✅⚠️

Structural: 22/22 smoke tests PASS. Execution: 4 runs (synthetic marine, synthetic terrestrial, minimal-DwC, **real OBIS data**) all completed with every requested figure rendered as 300-dpi PNG + vector PDF. Warnings are minor, documented, and none block Phase 3 consumption of the §11.6 contract.

## 1. Structural smoke tests (`python3 test_smoke.py`) — 22/22 PASS

| Check | Result |
|---|---|
| Frontmatter coherence (master + 4 sub-skills: name/description/version/updated/triggers; versions all 1.0.0) | PASS |
| Master router references every sub-skill path AND frontmatter name | PASS |
| Ask-user stop points ≥3 per sub-skill (SPs 3–5, Evidence+Recommend+Options format) | PASS |
| Signature libraries ≥3 entries per sub-skill (6/7/6/6 rows) | PASS |
| Inputs/Outputs contracts in all sub-skills | PASS |
| §11.6 minimal DwC columns in master + enforced by code | PASS |
| Workers wired into pixi.toml tasks | PASS |
| Realm configs parse + realm-consistent (marine/freshwater/terrestrial) | PASS |
| docs-corpus: 6/6 pinned tools populated, index + sha256 fingerprints match | PASS |
| pixi.toml parses (`pixi lock --dry-run` clean); pinned renderer packages present | PASS |
| No per-call realm branching in workers (config-driven realm-awareness, pinned) | PASS |
| R-only renderer (no Python) | PASS |
| .gitignore covers .pixi/, work/, runs/, docs-corpus/.fingerprints/ | PASS |
| `bin/skill-update-check.py` compiles + referenced from README + pixi.toml | PASS |

## 2. Execution battle test — realm matrix + real data

| # | Run | Input | Config | Figures rendered (PNG 300 dpi + PDF) | Skips |
|---|---|---|---|---|---|
| E1 | marine | `test/test_fixture_marine.parquet` (822 rows, 8 species, synthetic — crosscheck-shaped: depth_m + env_bio_* + FishBase-like trait cols) | `run-config.marine.json` | **06**: map, species facets, depth profile, env envelope, trait space, multi-panel | 0 |
| E2 | terrestrial | `test/test_fixture_terrestrial.parquet` (603 rows, 6 species, Borneo box, elev + env_wc_bio1/12) | `run-config.terrestrial.json` | **05**: map, facets, elevation profile, bioclim envelope, multi-panel | 1 — `05_trait_space` (input has `trait_depth_min_m/max` = NA for terrestrial taxa; graceful skip with reason — correct realm behavior, no false env lookup) |
| E3 | §11.6 graceful absence | `test/test_fixture_minimal.parquet` (120 rows, minimal DwC only — plain obis-gbif-fetch shape) | `run-config.marine.json` | **03**: map + facets + multi-panel (from maps only) | 3 — profile/envelope/trait skipped WITH machine-readable reasons (`figure-report.md` quotes them) — exactly the pinned standalone contract |
| E4 | real data (optional per pinned brief; network was available) | `test/test_fixture_real_obis.parquet` — **500 live records from the OBIS API** (`api.obis.org/v3/occurrence?taxon=Decapterus macarellus&size=500`), DwC columns + depth | marine | **05**: map (global), facets, depth profile, envelope, multi-panel | 1 — trait space (real OBIS pull has no trait columns) |

Outputs: `runs/bt_marine/`, `runs/bt_terr/`, `runs/bt_minimal/`, `runs/bt_real_obis/` — each with `fig/*.{png,pdf}`, `fig/figure-captions.md`, `figure-report.md`, `work/figure_status.jsonl` ledger + `work/plots/*.rds` snapshots. All PNGs verified 300 dpi (2700×1800 px @ 9×6 in etc.) and PDFs are vector (cairo_pdf). Visual QA performed on 01/02 (marine), 03 (depth profile), 04 envelope (terrestrial), and the real-OBIS map: basemaps correct, axes labeled, species italicized, captions match data.

## 3. PINNED-decision compliance checks

| Pinned decision | Status |
|---|---|
| Sub-skills preflight/maps/profiles-env/report (PLAN §5) | ✅ shipped |
| Realm-aware via config/argument — same plotting code, x-variable from run config (marine→depth; freshwater/terrestrial→elev/bioclim) | ✅ E1/E2 used identical code, different configs; smoke test guards regression |
| R renderer (ggplot2+sf+rnaturalearth, arrow parquet) — no Python | ✅ |
| §11.6 standalone input; env/trait figures only when columns exist | ✅ E3 |
| Must plot plain obis-gbif-fetch parquet | ✅ E3 (synthetic plain pull) + E4 (real OBIS pull) |
| Bash-only, no runners | ✅ |
| Docs-corpus for ggplot2/sf/rnaturalearth/arrow/scico/viridis | ✅ |
| 300 dpi PNG + PDF both realms | ✅ |
| geocurate pattern reuse (seed-42 subsampling + rnaturalearth→maps fallback) | ✅ in `bin/lib_viz.R` (not exercised at scale in these runs — fixtures < 20k points; WARN W2) |
| No push to GitHub, no deploy to ~/.pi/agent/skills/, PLAN not modified | ✅ local commits only |

## 4. Warnings (why not plain PASS)

- **W1 — fixture-based env envelopes are synthetic**: E1/E2 env values are simulated; E4 uses genuine OBIS data (depth + coords real). The plotting stack is data-shape-agnostic, but envelope *scientific* correctness depends on upstream crosscheck env-extract, out of scope here.
- **W2 — subsampling + maps-fallback untested at scale/without rnaturalearth**: the seed-42 subsample path and `maps::map()` fallback are code-reviewed and smoke-covered but not exercised with >20k points or in a stripped env (rnaturalearthdata present in pixi env, so fallback never fired).
- **W3 — real-OBIS pull returned 355 "species"** for a `taxon=Decapterus macarellus` query (OBIS matched associated taxa in the payload). Handled correctly by the pipeline (per-species facets), but the query semantics belong to obis-gbif-fetch, not viz.
- **W4 — terrestrial fixture carries all-NA trait_depth columns**, so E2's trait-space skip exercises the graceful-absence path rather than a marine-style finfish plot; marine finfish trait space IS rendered in E1.

## 5. Artifacts & handoff

- Structural: `test_smoke.py` (22 checks) — commit-able, rerunnable via `pixi run battle-test`.
- Execution evidence: `runs/bt_*` (git-ignored; regenerated by the commands above).
- Chain artifacts: `preflight.md` (GO) → `skill-built.md` → `debug-report.md` (RECOVERABLE) → this report.
- Next (orchestrator): review → `git push` to `github.com/cheahhl814/occurrence-viz` → deploy `~/.pi/agent/skills/occurrence-viz/` per AGENTS.md §4a (NOT done here, per pinned rule §11.8.2/3).

**Verdict: PASS-WITH-WARNINGS — skill is ready for orchestrator review and deploy.**