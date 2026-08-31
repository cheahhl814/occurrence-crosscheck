# OBIS API v3 — offline reference (marine-only)

Source: https://api.obis.org/ (Swagger UI, JS-rendered — not machine-fetchable via docs-ingest's HTML
strategies), cross-checked against https://manual.obis.org/. Endpoint shapes below verified with a live
`curl` (2026-08-31), which is authoritative for this snapshot.

## `/v3/occurrence` — marine occurrence corroboration

```
GET https://api.obis.org/v3/occurrence?scientificname=<name>&geometry=<WKT polygon>&size=1
```

Response envelope:

```json
{"total": <int>, "results": [...]}
```

`total` is the corroboration count used by `OUT_OF_RANGE` alongside GBIF, marine realm only
(realm-router gates `call_obis` to `realm == marine`). `size=1` keeps the response tiny — only `total`
matters here, not the record payload.

## `/v3/taxon/{scientificname}` — taxon lookup (reference, not used directly by this skill; WoRMS is
the marine taxonomic backbone of record per PLAN §4)

```
GET https://api.obis.org/v3/taxon/<scientificname>
-> 200 OK, verified live 2026-08-31
```

## Scope note (PLAN §2 scope table)

OBIS is marine-only. `realm-router` never sets `call_obis=True` for `freshwater` or `terrestrial` — this
skill must not call OBIS for those realms at all (pinned battle-test requirement), regardless of any
brackish/estuarine edge cases OBIS's own data model can represent.
