# WoRMS REST API — AphiaNameMatch / AphiaRecordsByMatchNames (marine-only)

Source: https://www.marinespecies.org/rest/ (REST API documented via its own `/rest/` root listing;
JS Swagger explorer not machine-fetchable, live endpoint verified directly). Fetched 2026-08-31.

## `/AphiaRecordsByMatchNames` — fuzzy name match, batched

```
GET https://www.marinespecies.org/rest/AphiaRecordsByMatchNames?scientificnames[]=<name>&marine_only=true
```

Verified live (2026-08-31): `GET .../AphiaRecordsByName/Gadus%20morhua -> 200 OK`.

Response shape: a **list of lists** — one inner list per queried name (supports batching multiple names
in one call via repeated `scientificnames[]=` params; this skill queries one name per call for simplicity
of the crosswalk cache, matching the "resolve on demand, cache forever" pattern — see PLAN §7 risk #1).
Each match record includes:

| Field | Notes |
|---|---|
| `AphiaID` | int — WoRMS's stable taxon ID; `urn:lsid:marinespecies.org:taxname:<AphiaID>` is the LSID form required by OBIS publishing (Phase 3, out of scope here) |
| `scientificname` | matched name |
| `status` | `accepted` / `unaccepted` / `uncertain` — `unaccepted` implies a synonym, still usable as an ID but worth surfacing |
| `match_type` | `exact` / `like` / `phonetic` / `near_1` / `near_2` |

**0 matches is expected and NOT an error** for marine queries on genuinely absent taxa; **>1 match is
ambiguous** and this skill routes it to `review_queue.csv` rather than guessing.

## marine_only=true

Restricts results to WoRMS records flagged as occurring in the marine realm (WoRMS itself carries some
brackish/freshwater taxa — PLAN §2 note — but the pinned battle-test contract for THIS skill only ever
calls WoRMS at all when `realm == marine`, so `marine_only=true` is belt-and-braces, not the primary
realm gate; the primary gate is `realm-router`'s `call_worms` flag).

## Rate limits

WoRMS asks for reasonable use (no documented hard per-second cap for the REST API as of this snapshot);
this skill calls WoRMS once per unique `scientificName` (cached in `crosswalk_cache.sqlite`), never
per-occurrence-point.
