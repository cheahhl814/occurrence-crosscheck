# skill-built.md — edna-crosscheck v1.0.0

Built: 2026-08-31. Builder: Claude Code (phases preflight→build→debug) + Pi (takeover: verification + finalization) after Claude Code hit its usage limit mid-finalization.

## File inventory

| Path | Role |
|---|---|
| `SKILL.md` | Orchestrator/router — 4-phase chain, realm awareness, links to PLAN (§4 spec, §11 contracts) |
| `preflight/preflight.py` + `preflight/SKILL.md` | Input ASV validation, realm declaration, run manifest (`params.json`) |
| `realm-router/realm_router.py` + `SKILL.md` | Load-bearing realm branching: backbone priority, env source, QC rules (PLAN §4.0) |
| `taxon-resolve/taxon_resolve.py` + `SKILL.md` | Crosswalk cache (sqlite): GBIF /species/match + WoRMS AphiaNameMatch + FishBase; ambiguous → review_queue.csv |
| `fishbase-traits/fishbase_traits.py`, `fishbase_pull.R` + `SKILL.md` | Trait pull (depth, trophic, body size); Python primary, R helper |
| `env-extract/env_extract.py` + `SKILL.md` | Realm-routed: Bio-ORACLE ERDDAP (bbox NetCDF → local point extraction; surface/benthic chosen from FishBase depth) vs WorldClim/CHELSA (direct HTTPS zips → rasterio) — bbox-download-once cache at `env-extract/.cache/` |
| `crosscheck/crosscheck.py`, `occurrence_lookup.py` + `SKILL.md` | OBIS/GBIF occurrence envelopes + flag emission (`OUT_OF_RANGE`, `ENVELOPE_VIOLATION`, `GENUS_ONLY`, `NOVEL_TAXON`, `ON_LAND`); flags, never silent drops |
| `bin/run-crosscheck.sh` | Main entry: fixture + realm → outputs |
| `bin/skill-update-check.py` | Self-update check (bioinfo-skill-creator §0.6) |
| `lib/netlog.py` | Network call logger → `work/call_log.jsonl` (used by battle-test assertions) |
| `test/test_smoke.py` | Structural smoke tests (84 checks) |
| `test/run_battle_test.sh` | Realm-matrix runner: same fixture × 3 realms + verifier |
| `test/verify_battle_test.py` | Network-call assertions + §11.2–§11.5 schema conformance (41 checks) |
| `test/fixtures/synthetic_asv.csv` | Synthetic ASV fixture |
| `test/battle-test-out/{marine,freshwater,terrestrial}/` | Real run outputs incl. `work/call_log.jsonl` |
| `docs-corpus/{gbif,obis,worms,fishbase,bio-oracle,worldclim-chelsa}/` | Offline docs snapshots (6 tools) |
| `pixi.toml`, `pixi.lock`, `params.json`, `preflight.md` | Env + run manifest + preflight artifacts |

## Readiness

- Smoke tests: 84/84 PASS
- Battle-test: 41/41 assertions PASS (realm-matrix, real network calls)
- Ready for Phase 4 report → `battle-test-report.md` (see it for verdict)