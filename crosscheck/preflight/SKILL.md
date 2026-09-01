---
name: edna-crosscheck-preflight
description: Validates the nf-edna ASV/occurrence table (columns, marker, spatial scope) and declares the run's realm, writing the pinned params.json run manifest (PLAN §11.1) that every other sub-skill consumes.
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "edna-crosscheck preflight"
  - "validate ASV table for crosscheck"
---

# preflight/edna-crosscheck-preflight

## Inputs
- Raw ASV/occurrence CSV from `nf-edna` / `nf-edna-nanopore`, or any DwC-shaped table with
  `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate`.
- User-declared `realm` (`marine`|`freshwater`|`terrestrial`), `marker` (e.g. `12S`).

## Outputs
- `params.json` — PLAN §11.1 schema, byte-for-byte (shared contract with two sibling skills).

## Procedure
```bash
python3 preflight.py <input.csv> <realm> <marker> <out_params.json> [minLon minLat maxLon maxLat]
```
Verifies required columns present, realm is one of the three valid values, at least one data row exists.
Computes a padded bbox from the data if not supplied. Exits non-zero (NO-GO) on any check failure.

`--require-confirm` (SP-10 backstop, see `../SKILL.md` §0.5): when the buffer resolves to `auto`
mode on a degenerate input extent, preflight FAILs (exit 1) instead of only WARNing, forcing an
explicit `--buffer-km`/`--buffer-deg`/`--bbox` declaration. With a user-declared buffer it instead
prints `preflight: SP-10 confirmed (buffer=user-...)` and proceeds. Without the flag, behavior is
unchanged (WARN only).

## Ask-user stop points (resolved per task pins — recorded here for the evidence trail)

**SP1 — realm declaration.** Evidence: eDNA projects are realm-specific per run (PLAN §2). Recommend:
require `--realm` as a mandatory CLI arg, no default guess. Decision (pinned): mandatory arg, preflight
hard-fails with no realm inferred — see `preflight.md §Deviations` for any case this couldn't be
satisfied.

**SP2 — FishBase client (Python REST vs R rfishbase).** Evidence: no `fishbaseapi` package on PyPI;
`fishbase.ropensci.org` (the historical live REST host) returns 404/blocked in this environment.
Recommend: R `rfishbase` (CRAN) — resolves cleanly once `libuv` is added to `pixi.toml`, verified live
against Atlantic cod (SpecCode 69, depth 0-600m). Decision (pinned + verified): R rfishbase via
`Rscript` subprocess. Full resolution trail in `preflight.md §FishBase client decision`.

**SP3 — MZGdb scope.** Evidence: PLAN §7 risk #4 flags MZGdb as primer-design-relevant, deferrable from
Phase 1. Recommend: exclude MZGdb entirely from `edna-crosscheck` v1. Decision (pinned): excluded — no
MZGdb snapshot ships with this skill.

## Signature library

| stderr / evidence pattern | likely cause | fix |
|---|---|---|
| `FAIL input missing required columns` | ASV table lacks DwC-shaped columns | re-export from nf-edna with `scientificName`/`decimalLatitude`/`decimalLongitude`/`eventDate`, or map columns before running |
| `FAIL invalid realm` | `--realm` typo or omitted | pass exactly one of `marine`, `freshwater`, `terrestrial` |
| `FAIL input has zero data rows` | empty/header-only CSV, or upstream ASV table filtered everything out | check nf-edna's taxonomy-assignment step output before re-running crosscheck |
