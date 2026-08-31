# Battle-test report — edna-crosscheck v1.0.0

Run:       skills/edna-crosscheck
Generated: 2026-08-31 (Phase 4, bioinfo-skill-creator chain)
Mode:      structural smoke tests + realm-matrix EXECUTION (real network calls, no mocking)

## Overall verdict

**PASS** ✅

84/84 structural smoke checks + 41/41 battle-test assertions (PLAN §9 realm-matrix acceptance criteria). The finalization was completed by Pi after Claude Code (which built and executed the realm-matrix runs) hit its usage limit mid-finalization; all numbers below are from Pi re-running both suites independently against the real output directories.

## 1. Structural smoke tests — 84/84 PASS

Highlights (full output in session log):

- All sub-skill SKILL.md compile/parse with coherent frontmatter (`name`, `version: 1.0.0`, `updated`, `triggers`)
- Every module compiles: `crosscheck.py`, `occurrence_lookup.py`, `env_extract.py`, `taxon_resolve.py`, `preflight.py`, `realm-router`, `skill-update-check.py`
- `bin/run-crosscheck.sh` present + executable; `skill-update-check` wired into README + pixi.toml
- docs-corpus populated for all 6 pinned tools (gbif, obis, worms, fishbase, bio-oracle, worldclim-chelsa)
- Git repo initialized (first commit added post-verification by takeover session)

## 2. Realm-matrix battle test (PLAN §9) — 41/41 PASS

Same synthetic fixture (`test/fixtures/synthetic_asv.csv`) run 3× with real network calls:

### Network-call assertions (the core realm-isolation proof)

| Assertion | Result |
|---|---|
| marine run called obis, worms, bio-oracle | PASS |
| freshwater run did NOT call obis/worms/bio-oracle; used worldclim-chelsa | PASS |
| terrestrial run did NOT call obis/worms/bio-oracle; used worldclim-chelsa | PASS |
| Evidence: per-run `work/call_log.jsonl` + successfully populated `work/env_values.csv` |

### Missing-AphiaID is not a false-flag source for non-marine realms (PLAN risk #8)

- freshwater + terrestrial: `worms_AphiaID` all-null — expected, not an error → PASS
- Zero flags caused BY missing AphiaID in non-marine realms → PASS

### Schemas vs PLAN §11.2–§11.5 (all 3 realms)

- `enriched.parquet` has all §11.2 columns (scientificName, backbones IDs, traits, env_*, qc_flags, qc_level, realm) → PASS
- `crosscheck_report.json` has run/summary/issues; 5 flag keys → PASS
- `flagged_occurrences.tsv` has `signoff_status`, default `pending` → PASS
- `review_queue.csv` has §11.5 columns → PASS
- `params.json` realm matches run → PASS

### QC behavior sanity (crosscheck_report.json summaries)

| Realm | OUT_OF_RANGE | ENVELOPE_VIOLATION | NOVEL_TAXON | Notes |
|---|---|---|---|---|
| marine | 4 | **3** | 1 | Bio-ORACLE × FishBase depth envelope active |
| freshwater | 4 | **0** | 1 | Correct — no marine env lookup, wc/CHLSA envelope (fixture within range) |
| terrestrial | 4 | **0** | 1 | Correct — same |

The marine-only ENVELOPE_VIOLATION firing (3) while non-marine runs stay at 0 is exactly the designed realm isolation: the freshwater/terrestrial runs used elevation/bioclim envelopes instead, and the fixture is in-range for those.

## 3. Warnings

1. Fixture is synthetic (4 records/small); acceptable per PLAN §11.8 rule 4 for structural tests. First run on a real ASV table (e.g. AZAM_NSPSF) remains the recommended shakedown before production use.
2. Bio-ORACLE extraction verified via "network call OR verified cache hit" (shared skill-level `env-extract/.cache/` by design — documented in docs-corpus). A first-ever run in a fresh clone will re-download bbox rasters.
3. `env-extract/.cache/` (~MBs of NetCDF/GeoTIFF) is currently inside the skill tree but gitignored — confirm before packaging.

## Verdict: PASS

Phase 1 acceptance criteria from PLAN §9 are met. Skill is ready for user-level shakedown (`pixi run crosscheck <asv> --realm <r>`) and for contract consumption by occurrence-viz (§11.6) / occurrence-publish (§11.4, §11.7).