---
name: edna-crosscheck-fishbase-traits
description: Bulk-pulls FishBase depth range / trophic level / body-size traits per taxon via the rfishbase R package (CRAN), for marine and freshwater finfish; pass-through for terrestrial realm.
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "edna-crosscheck fishbase traits"
  - "pull fishbase depth trophic level"
---

# fishbase-traits/edna-crosscheck-fishbase-traits

## Inputs
- `names_file` (same unique-name list as taxon-resolve).
- `routing.json` — pass-through short-circuit when `realm == terrestrial`.

## Outputs
- `fishbase_pull.json` — `{scientificName: {SpecCode, DepthRangeShallow, DepthRangeDeep, Length,
  trophic_level}}`. Consumed by `env-extract` (surface/benthic layer choice) and `crosscheck.py` (final
  trait columns + `fishbase_SpeCode`).

## Procedure
```bash
python3 fishbase_traits.py <names_file> <routing.json> <work_dir>
```
Delegates to `fishbase_pull.R` (Rscript subprocess) unless `realm == terrestrial`, in which case it
writes an empty `{}` without spawning R at all. Failure of the R subprocess (missing Rscript, rfishbase
not installed, network failure) degrades to an empty trait table rather than crashing the run — trait
columns simply stay null with the reason implicit in the sub-skill's own stderr log.

## Ask-user stop points

**SP1 — FishBase client: Python REST vs R rfishbase.** See `preflight/SKILL.md` SP2 for the full
Evidence/Recommend/Decision record; resolved here as: R rfishbase via `Rscript` subprocess, CRAN install
(needs `libuv` added to `pixi.toml` for the `fs` package's C dependency — added and verified).

**SP2 — SeaLifeBase fallback for non-fish marine taxa.** Evidence: PLAN §4 calls for a SeaLifeBase
fallback but explicitly scopes it out of "do now". Recommend: skip in v1. Decision (pinned scope): not
implemented — non-fish taxa simply get no FishBase trait row (same as any unmatched name).

**SP3 — trophic level source.** Evidence: `rfishbase::species()` doesn't carry `FoodTroph` directly; it
lives in the separate `ecology()` table, joined by Genus+Species. Recommend: a best-effort second R call
per run (not per-taxon) to `ecology()`, tolerating `NA` if the taxon has no ecology row. Decision: implemented
exactly this way in `fishbase_pull.R`.

## Signature library

| stderr / evidence pattern | likely cause | fix |
|---|---|---|
| `Rscript not found; emitting empty trait table` | R/Rscript not on PATH in this pixi env | `pixi run setup-fishbase` (installs rfishbase) requires `r-base` in `pixi.toml` — confirm `pixi list | grep r-base` |
| `fishbase_pull.R failed rc=1: ... uv.h: No such file or directory` | `fs` R package (a rfishbase dependency) needs libuv dev headers | add `libuv` to `pixi.toml` `[dependencies]` (conda-forge has it) and re-run `pixi run setup-fishbase` — this was hit and fixed during this skill's own build |
| trait columns all null even for common taxa like "Gadus morhua" | `species(names)` matched on exact Genus+Species string; a name with subspecies/author suffix won't match | strip authorship/rank qualifiers before calling fishbase-traits, or rely on `acceptedScientificName` from taxon-resolve instead of the raw `scientificName` |
