# GBIF Species + Occurrence API — offline reference

Source: https://techdocs.gbif.org/en/openapi/v1/species , https://techdocs.gbif.org/en/openapi/v1/occurrence ,
https://www.gbif.org/developer/species , https://www.gbif.org/developer/occurrence
Ingested via docs-ingest Strategy 5 (manual fetch) + verbatim `curl` capture against the live API
(the Swagger UI pages are JS-rendered and did not yield text via automated fetch — the request/response
shapes below are captured directly from the live endpoint, which is authoritative and version-exact).
Fetched: 2026-08-31.

## `/v1/species/match` — fuzzy/exact taxonomic name match (used by taxon-resolve)

```
GET https://api.gbif.org/v1/species/match?name=<scientificName>&verbose=true
```

Verified live request/response (2026-08-31):

```
GET https://api.gbif.org/v1/species/match?name=Gadus%20morhua
-> 200 OK
```

Key response fields:

| Field | Type | Notes |
|---|---|---|
| `usageKey` | int | GBIF taxonKey — this is `gbif_taxonKey` in `enriched.parquet` |
| `scientificName` | string | canonical name with authorship |
| `species` | string | accepted species-rank name (no authorship) |
| `matchType` | enum | `EXACT` / `FUZZY` / `HIGHERRANK` / `NONE` |
| `confidence` | int 0-100 | match confidence; taxon-resolve treats `FUZZY` with `confidence < 90` as ambiguous |
| `status` | enum | `ACCEPTED` / `SYNONYM` / `DOUBTFUL` |
| `rank` | enum | `SPECIES`, `GENUS`, etc. — `HIGHERRANK` matchType + `rank=GENUS` -> `GENUS_ONLY` flag |

`matchType=NONE` means no match at all -> `taxon_match_status=unresolved` -> `NOVEL_TAXON` flag.

## `/v1/occurrence/search` — occurrence corroboration (used by crosscheck/occurrence_lookup.py)

```
GET https://api.gbif.org/v1/occurrence/search?scientificName=<name>&geometry=<WKT polygon>&limit=0
```

`limit=0` returns only the `count` field (cheap existence check — no full record fetch). One call per
unique (taxon, bbox), never per-point. `count == 0` combined with OBIS `total == 0` (marine) or alone
(non-marine) drives the `OUT_OF_RANGE` flag.

## Rate limits / etiquette

No API key required for read GETs. GBIF publishes no hard documented rate limit for these endpoints but
recommends batching (SQL downloads / occurrence cubes for bulk use — see PLAN §10) rather than looping
per-point; this skill never issues a per-occurrence-point call to GBIF, only per-unique-taxon.
