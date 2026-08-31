# FishBase — offline reference (rfishbase R package, CRAN)

Source: https://docs.ropensci.org/rfishbase/ , https://github.com/ropensci/rfishbase , CRAN package page
https://cran.r-project.org/web/packages/rfishbase/index.html . Fetched/verified 2026-08-31 via a live
install + query in this skill's own pixi env (see preflight.md §FishBase client decision).

## Architecture (important — this is NOT a live per-name REST API anymore)

As of rfishbase >= 4.x, the package does **not** call a live `fishbaseapi` REST endpoint
(`fishbase.ropensci.org`, the historically documented API host, returns 404 in this sandbox — it appears
deprecated/retired). Instead, `rfishbase::species()`, `::ecology()`, etc. pull versioned **Parquet
snapshot tables** from a Source Cooperative S3 bucket
(`s3://us-west-2.opendata.source.coop/cboettig/fishbase/`) via `duckdbfs`, cache them locally, and query
them with DuckDB. This is a *bulk-download-once, query-locally* pattern — a natural fit for this skill's
"never per-point remote calls" rule, and arguably a better fit than a live REST API would have been.

## R usage (this skill's actual call path — `fishbase-traits/fishbase_pull.R`)

```r
library(rfishbase)
species(c("Gadus morhua", "Salmo salar"))       # SpecCode, DepthRangeShallow/Deep, Length, ...
ecology(c("Gadus morhua"))                       # FoodTroph (trophic level), habitat fields
```

Verified live output for `species("Gadus morhua")` (2026-08-31, this sandbox):

| Genus | Species | SpecCode | DepthRangeShallow | DepthRangeDeep | Length |
|---|---|---|---|---|---|
| Gadus | Gadus morhua | 69 | 0 | 600 | 200 |

## Key fields used by this skill

| rfishbase field | enriched.parquet column |
|---|---|
| `SpecCode` | `fishbase_SpeCode` |
| `DepthRangeShallow` | `trait_depth_min_m` |
| `DepthRangeDeep` | `trait_depth_max_m` |
| `Length` (cm) | `trait_body_size_cm` |
| `ecology()$FoodTroph` | `trait_trophic_level` |

## Non-fish / SeaLifeBase

PLAN §4 calls for a SeaLifeBase fallback for non-fish marine taxa. Not implemented in this v1 (finfish
only, per the task's build scope) — `fishbase_pull.R` simply returns no row for non-fish names, and
`crosscheck.py` nulls the trait columns with the taxon's row otherwise unaffected. Noted as a v2 item.

## Terrestrial realm

FishBase is a fish/aquatic-only database. For `realm=terrestrial`, `fishbase-traits` is a documented
pass-through (no R call made at all) — see PLAN §4.
