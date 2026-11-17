---
name: edna-crosscheck
description: 'Cross-checks eDNA occurrence observations (from nf-edna/ednanopore ASV tables) against GBIF/OBIS/WoRMS/FishBase taxonomic backbones and Bio-ORACLE/WorldClim-CHELSA environmental envelopes, realm-aware (marine/freshwater/terrestrial). Phase 1 of a 3-skill eDNA meta-stack (PLAN-marine-edna-meta-skill.md). Emits enriched.parquet, crosscheck_report.json, flagged_occurrences.tsv, review_queue.csv — flags, never silently drops records. Use when the user asks to "cross-check eDNA results", "validate ASV table against GBIF/OBIS", "QC eDNA occurrences", or "ground-truth eDNA detections".'
version: 1.1.0
updated: "2026-11-11"
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
disable-model-invocation: true
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

## 0.5 Ask-User Stop Points (runtime parameters)

> **SP-10 — Buffer scale.** Evidence: single-site degenerate extent + auto 0.25-deg buffer produced
> 39/48 false-DISCORDANT verdicts in the first battle test (defect D1); `preflight.py` already
> WARNs on this combo but proceeds. Recommend: regional `--buffer-km` (100 km estuary/coastal,
> 2000 km regional biogeographic). Auto-pick only when input extent spans multiple distinct sites.
> Confirm or pick one of: A) `--buffer-km 100` B) `--buffer-km 2000` C) explicit `--bbox`.
> Auto-pick condition: proceeds unasked only when the input extent already spans multiple distinct
> sites (non-degenerate); for a degenerate single-site extent, ask before proceeding. Backstop: run
> `preflight.py --require-confirm` to turn the WARN into a hard FAIL (exit 1) on auto+degenerate,
> so an unattended run cannot silently inherit the tight default — see preflight/SKILL.md.

> **SP-11 — Concordance ring R (`--near-km`, default 100 in viz).** Evidence: merged-ring semantics
> (see Operational notes) make R both the map ring and the verdict threshold; the 2024K1 battle test
> used 150. Recommend: 150 for regional marine surveys. Confirm or pick one of: A) 50 (high-res
> coastal) B) 150 (regional marine) C) custom.
> Auto-pick condition: never silently auto-pick; if the user already endorsed a project-level R,
> apply it and log the source instead of re-asking.

> **SP-12 — Detection-site coordinate provenance.** Evidence: 2024K1 inputs all share one placeholder
> centroid (2.9857056, 101.2587923) because per-sample coords were absent. Recommend: confirm the
> placeholder is acceptable or supply real per-sample coordinates. Confirm or pick one of:
> A) confirm centroid B) supply real coords C) abort for re-export.
> Auto-pick condition: never for single-point inputs — ask whenever all input rows share one
> coordinate; a wrong site shifts every distance verdict.

> **SP-13 — Realm routing when taxa span realms.** Evidence: mixed-taxa inputs occasionally resolve
> partly outside the declared realm. Recommend: trust the declared realm when the vast majority of
> taxa clearly belong to it. Confirm or pick one of: A) keep declared realm, flag minority taxa
> B) ask which realm governs OBIS/WoRMS marine-only gating for the minority taxa.
> Auto-pick condition: auto-pick A when >=95% of detected taxa clearly resolve to the declared
> realm; otherwise ask.

## Network scope (read-only, no publishing)

GET-only calls to GBIF (`api.gbif.org`), OBIS (`api.obis.org`, marine realm only), WoRMS
(`marinespecies.org/rest`, marine realm only), FishBase (via `rfishbase`'s Source Cooperative S3
parquet snapshots), Bio-ORACLE ERDDAP (`erddap.bio-oracle.org`, marine realm only), WorldClim
(`geodata.ucdavis.edu`, freshwater/terrestrial only). No API keys, no writes, no publishing — that's
`occurrence-publish` (Phase 3, a sibling skill), out of scope here.

**Contact-attribution User-Agent (SP-4):** every HTTP call carries a `User-Agent: edna-crosscheck/<ver> (mailto:<email>)`
header built from the user's `--user-email` (collected at preflight, recorded in `params.json:user_email`,
propagated to every NetLog consumer). GBIF's API contact-attribution policy
(https://www.gbif.org/api) requires a real contact so they can reach the user about rate-limits,
broken queries, or attribution. preflight HARD-FAILs if `--user-email` is missing or malformed;
the agent MUST ask the user for this value before invoking the orchestrator (do not invent,
do not default, do not read from git config). Same value is also embedded in DwC-A `eml.xml`
by the `publish` sub-skill for GBIF/OBIS dataset attribution.

## Sub-skills

1. [`preflight/`](preflight/SKILL.md) — input validation + run manifest. Requires `--user-email` (SP-4).
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

## Operational notes

Design decisions that constrain maintenance (see git history for how they landed):

- **Ring geometry is geodesic.** The concordance ring (`--near-km R`) is a true great-circle
  circle: occurrence counts use a server-side `geometry=<64-point POLYGON>` filter on both GBIF
  and OBIS (antimeridian circles fall back to a cos(lat)-corrected bbox with a stderr warning);
  `context_records.py` double-checks rows with a client-side haversine filter. Shared helpers
  live in `lib/geo.py` (`ring_coords`, `circle_wkt`, `haversine_km`, `corrected_box`). Multi-site
  extents keep the box window with a cos(lat)-corrected longitude pad.
- **Merged-ring semantics (PLAN §11.13).** ONE `--near-km R` governs the map ring, the concordance
  threshold, and the verdict (CONCORDANT = record ≤ R; DISCORDANT = known beyond R; NO_RECORD =
  absent everywhere checked). The old separate fetch buffer is now only an internal
  data-collection region; `context_records.py --outside-cap N` bounds the beyond-ring sample.
  Env/WorldClim sampling regions are unchanged (buffer stays an internal env-envelope setting).
- **basisOfRecord filtering.** GBIF applies the allow-list server-side (repeated
  `basisOfRecord=` params: HUMAN_OBSERVATION, MACHINE_OBSERVATION, MATERIAL_SAMPLE, OBSERVATION —
  MATERIAL_SAMPLE kept because it is this project's own eDNA basis). OBIS silently ignores the
  parameter server-side (live-verified), so full-record fetches filter client-side, and the
  count-only calls go through `lib/netlog.py::obis_filtered_count` (cheap `size=0` raw count,
  then one page up to `OBIS_COUNT_FILTER_CAP` = 10000, exact up to the cap).
- **habitat-iucn candidate parsing.** `read_candidates()` parses `candidate_species`
  (binomial = first two tokens), accepts `scientificName` for compat, and maps `genus`/`rank`
  with `candidate_of`/`candidate_rank` fallbacks (matches `species_images.load_candidates`).
- **Runtime stop points.** SP-10..SP-13 (§0.5 above) are the runtime ask-user points; keep them
  in sync with `preflight.py --require-confirm`.

## Dependencies → biodb-fetch (shared data lake)

Consumes [biodb-fetch](https://github.com/cheahhl814/biodb-fetch) v1.0.0 (deployed at `~/.agents/skills/biodb-fetch/`) for the marine-backbone and occurrence lookups the crosscheck phase performs:

- `scripts/occurrence_marine.py` — OBIS occurrence/checklist/dataset pulls (public tier; WKT polygon, year-window, depth, datasetid filters). biodb-fetch owns OBIS rate spacing and manifest recording.
- `scripts/taxonomy.py worms` — WoRMS AphiaID resolution (+ synonyms/vernaculars) for OBIS joins.
- `scripts/taxonomy.py colxr` — Catalogue of Life XR lookups (GBIF's default taxonomy since its Backbone froze in 2023).
- **Freshness rule (critical for crosschecking)**: OBIS occurrence data grows over time — biodb-fetch cache rows carry `retrieval_date`. For a current-state comparison pass `--refresh`; never mix cached and freshly-pulled rows for the same species/region window in one crosscheck.
- **Contract v2**: locate files via the emitted `manifest.tsv` (`cache=hit` rows point into the shared store) — never parse biodb-fetch internals.
- FishBase / Bio-ORACLE / WorldClim lookups stay inside this skill (out of biodb-fetch's scope).
- **Degradation**: biodb-fetch unavailable → use this skill's direct API calls and note the deviation in the crosscheck report.
