---
name: edna-crosscheck
description: 'Cross-checks eDNA occurrence observations (from nf-edna/nf-edna-nanopore ASV tables) against GBIF/OBIS/WoRMS/FishBase taxonomic backbones and Bio-ORACLE/WorldClim-CHELSA environmental envelopes, realm-aware (marine/freshwater/terrestrial). Phase 1 of a 3-skill eDNA meta-stack (PLAN-marine-edna-meta-skill.md). Emits enriched.parquet, crosscheck_report.json, flagged_occurrences.tsv, review_queue.csv — flags, never silently drops records. Use when the user asks to "cross-check eDNA results", "validate ASV table against GBIF/OBIS", "QC eDNA occurrences", or "ground-truth eDNA detections".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "cross-check eDNA results"
  - "validate ASV table against GBIF"
  - "edna-crosscheck"
  - "QC eDNA occurrences"
  - "ground-truth eDNA detections"
  - "realm-aware eDNA validation"
requires:
  - "pixi (this skill's pixi.toml/pixi.lock pins python 3.11 + R 4.5 envs)"
  - "network access (read-only GETs to GBIF, OBIS, WoRMS, FishBase-via-rfishbase's S3 bucket, Bio-ORACLE ERDDAP, WorldClim)"
---

# Meta-skill: edna-crosscheck

Phase 1 of the eDNA meta-skill stack (merged into `../../occurrence-crosscheck`) described in `../../../PLAN-marine-edna-meta-skill.md`. This

### Input modes (three)

| Mode | Input | Runner | Output |
|---|---|---|---|
| **asv** (classic) | 4-col occurrence table \(`scientificName, decimalLatitude, decimalLongitude, eventDate`\) | `pixi run crosscheck <csv> <realm> <marker> <out>` | enriched.parquet + flags |
| **species** (inverted) | .txt list or .csv with scientificName col | `pixi run species-list <input> <realm> <out> [record_limit]` | species_envelopes.csv \= known GBIF/OBIS extent + FishBase traits (the envelope IS the output) |
| **coords** (inverted) | .csv with decimalLatitude/decimalLongitude \(+point_id\) | `pixi run coordinates-checklist <csv> <realm> <out> [radius_deg] [max_taxa]` | expected_species.csv \(OBIS checklist realm-flag-filtered + GBIF facets, backbone-resolved\) + env_snapshot.csv + review_queue.csv |
| **genus-narrow** (D) | `.csv` with `scientificName` (genus-only, e.g. from idtaxa) + detection coords | `pixi run genus-narrow <csv> <realm> <out> [--buffer-km N] [max_sp]` | genus_candidates.csv — candidate species per genus recorded within the buffer, ranked by corroboration (GBIF facet + OBIS checklist realm-filtered, BOLD/author-citation placeholders pruned) |
| **habitat-iucn** (F, v2.5.0) | `.csv` with `scientificName`, or one-name-per-line `.txt` | `pixi run habitat-iucn <list.csv> <work_dir> [--candidates <candidate_images.csv>]` | habitat_iucn.csv (§11.11) — WoRMS habitat flags (marine_only=false) + GBIF IUCN category per taxon, detected + candidate species. Flags never drops; cache-warm safe. Consumed by viz `--habitat` (map subtitles + IUCN-colour-coded sheet tiles). |
| **species-images** (E, v2.3.0) | `.csv` with `scientificName` column, or one-name-per-line `.txt` | `pixi run species-images <list.csv> <work_dir>` | species_images.csv + images/ cache — ONE citable photo per binomial with full citation chain (source, license SPDX, creator, occurrence URL). iNat-first, GBIF fallback (96% measured coverage), FishBase never embedded. Flags never drops: cc-best / by-nc (attribution-required) / flag-no-license / flag-all-rights-reserved (URL kept, file NOT cached) / flag-no-image / flag-ambiguous-taxon. Cache-warm safe. Consumed by viz `--images` (fig 07 contact sheet + per-species map thumbnails). `--candidates <genus_candidates.csv>` mode predicts species for genus-only ASVs -> candidate_images.csv (§11.10). |
SKILL.md is a router — it does not contain the QC logic itself. Read this file, then invoke
`bin/run-crosscheck.sh` (bash-first orchestrator) which chains the 6 sub-skills in a hard order.

## Sub-skill order (hard dependency, PLAN §4/§7 risk #3)

```
preflight -> realm-router -> taxon-resolve -> fishbase-traits -> env-extract -> crosscheck
```

`realm-router` is the ONLY place `realm` if-statements live. Every other sub-skill reads
`routing.json` instead of branching on realm. `fishbase-traits` must run before `env-extract`
because the marine surface-vs-benthic layer choice depends on the FishBase depth range.

## Quick start

```bash
cd skills/edna-crosscheck
pixi install
pixi run setup-fishbase          # one-time: installs rfishbase from CRAN (needs libuv, already pinned)
pixi run crosscheck <input.csv> <realm> <marker> <out_dir>
# e.g.
pixi run crosscheck test/fixtures/synthetic_asv.csv marine 12S /tmp/edna-run-marine
```

## Outputs (PLAN §11 pinned schemas — shared with the occurrence-viz and occurrence-publish sibling
skills being built in parallel; do not change these without updating PLAN §11 and re-verifying all
three skills)

| File | Schema |
|---|---|
| `params.json` | §11.1 |
| `enriched.parquet` | §11.2 |
| `crosscheck_report.json` | §11.3 |
| `flagged_occurrences.tsv` | §11.4 |
| `review_queue.csv` | §11.5 |

## Network scope (read-only, no publishing)

GET-only calls to GBIF (`api.gbif.org`), OBIS (`api.obis.org`, marine realm only), WoRMS
(`marinespecies.org/rest`, marine realm only), FishBase (via `rfishbase`'s Source Cooperative S3
parquet snapshots), Bio-ORACLE ERDDAP (`erddap.bio-oracle.org`, marine realm only), WorldClim
(`geodata.ucdavis.edu`, freshwater/terrestrial only). No API keys, no writes, no publishing — that's
`occurrence-publish` (Phase 3, a sibling skill), out of scope here.

## Sub-skills

1. [`preflight/`](preflight/SKILL.md) — input validation + run manifest.
2. [`realm-router/`](realm-router/SKILL.md) — the load-bearing realm-branching sub-skill.
3. [`taxon-resolve/`](taxon-resolve/SKILL.md) — WoRMS/GBIF/FishBase crosswalk cache; the #1 engineering
   risk per PLAN §7.
4. [`fishbase-traits/`](fishbase-traits/SKILL.md) — depth/trophic/body-size traits via rfishbase.
5. [`env-extract/`](env-extract/SKILL.md) — Bio-ORACLE (marine) / WorldClim-CHELSA (freshwater,
   terrestrial), bulk-download-once + local extraction.
6. [`crosscheck/`](crosscheck/SKILL.md) — final assembly + QC flags.

## Docs-corpus

`docs-corpus/{gbif,obis,worms,fishbase,bio-oracle,worldclim-chelsa}/README.md` — offline reference
snapshots of every upstream API/data source this skill talks to, built per the `docs-ingest` skill's
conventions (verbatim live-verified request/response captures where the source's own docs pages are
JS-rendered and not machine-fetchable).

## Self-update check

```bash
pixi run update-check
```
See `bin/skill-update-check.py`.

## Evidence trail

`preflight.md` (input validation, tool audit, FishBase client decision, ask-user stop-point record,
§Deviations), `params.json`, `skill-built.md`, `battle-test-report.md` (structural smoke tests +
realm-matrix battle test with real network-call evidence).
