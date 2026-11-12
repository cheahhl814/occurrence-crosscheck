---
name: edna-crosscheck-taxon-resolve
description: Builds/updates the scientificName-keyed taxon crosswalk cache (sqlite) against WoRMS, GBIF, and FishBase; ambiguous or unresolved matches go to review_queue.csv, never silently auto-resolved. PLAN §7 risk #1 — the highest-engineering-risk sub-skill in this build.
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "edna-crosscheck taxon resolve"
  - "resolve scientificName crosswalk"
disable-model-invocation: true
---

# taxon-resolve/edna-crosscheck-taxon-resolve

## Inputs
- `names_file` — one `scientificName` per line (unique names from the input occurrence table).
- `routing.json` (from realm-router; gates whether WoRMS is queried at all).

## Outputs
- `crosswalk_cache.sqlite` — keyed on `scientificName`, one row per unique name ever resolved by this
  skill install (append-only cache; a name already cached is never re-queried).
- `review_queue.csv` — PLAN §11.5 schema, rows for every `ambiguous`/`unresolved` name this run.

## Procedure
```bash
python3 taxon_resolve.py <names_file> <routing.json> <work_dir>
```
Query order (per task pin): WoRMS (marine-only, gated by `routing.call_worms`) -> GBIF `/species/match`
(universal, always queried) -> FishBase (deferred to the `fishbase-traits` sub-skill that runs next;
`fishbase_SpecCode` is filled in during final assembly in `crosscheck.py`, see module docstring for why).
`acceptedScientificName` defaults to the GBIF backbone name.

## Ask-user stop points

**SP1 — GBIF fuzzy-match confidence threshold for auto-accept.** Evidence: GBIF returns `matchType=FUZZY`
with a `confidence` score; a low-confidence fuzzy match is exactly the "bad join poisons every downstream
flag" risk PLAN §7 #1 warns about. Recommend: auto-accept `FUZZY` only at `confidence >= 90`; below that,
route to review. Decision (pinned intent: "any... low-confidence fuzzy match... goes to review_queue.csv"):
threshold implemented at 90.

**SP2 — WoRMS >1 candidate handling.** Evidence: `AphiaRecordsByMatchNames` can return multiple hits for
one query name (homonyms, subspecies). Recommend: never pick the first — always ambiguous. Decision
(pinned: "multiple candidates... never silently auto-resolved to a guess"): implemented exactly this way.

**SP3 — missing AphiaID for non-marine realms.** Evidence: PLAN §7 risk #8 — treating a missing AphiaID
as a taxonomic failure for freshwater/terrestrial would false-flag every record. Recommend: don't even
query WoRMS for those realms (realm-router already gates this), so the column is NULL by construction,
never contributing to `ambiguous`/`unresolved` status. Decision (pinned): implemented — `missing_aphia_is_error`
in routing.json is `False` for freshwater/terrestrial and this sub-skill never calls WoRMS for them.

## Signature library

| stderr / evidence pattern | likely cause | fix |
|---|---|---|
| every name lands in `review_queue.csv` with empty `gbif_candidates` | GBIF API unreachable / rate-limited / DNS failure | check `call_log.jsonl` for `gbif` entries with `status: null` and an `error` string; retry once network is confirmed |
| WoRMS calls return HTTP 204 for every name even on known marine taxa | `marine_only=true` filtering out a taxon that's WoRMS-listed as brackish/estuarine only | drop `marine_only=true` for that specific lookup if the taxon is a known euryhaline/brackish species (manual override, not automatic) |
| `sqlite3.OperationalError: database is locked` | two runs writing `crosswalk_cache.sqlite` concurrently | this skill has no multi-run lock (ponytail: single global lock, add per-run sqlite file if concurrent runs are needed) — don't run two crosscheck invocations against the same work_dir at once |
