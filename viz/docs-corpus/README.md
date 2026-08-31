# docs-corpus — occurrence-viz

Offline Markdown snapshot of upstream tool docs, generated with the docs-ingest
skill convention (GitHub-repo strategy; fallback chain: verbatim capture → repo
docs → web). Fingerprinted in `.fingerprints/sha256.md` — battle-test checks
every file still matches and refetches drift.

| Package | Dir | Sources | Captured |
|---|---|---|---|
| ggplot2 | `ggplot2/` | tidyverse/ggplot2 README (main) + ggplot2.tidyverse.org function-reference index | 2026-08-31 |
| sf | `sf/` | r-spatial/sf README (main) | 2026-08-31 |
| rnaturalearth | `rnaturalearth/` | ropensci/rnaturalearth README (master) | 2026-08-31 |
| arrow (R) | `arrow-r/` | apache/arrow `r/README.md` + arrow.apache.org/docs/r index (converted) | 2026-08-31 |
| scico | `scico/` | thomasp85/scico README | 2026-08-31 |
| viridis | `viridis/` | sjmgarnier/viridis README (master) | 2026-08-31 |

Rendered with the offline agent in mind: read these instead of hallucinating
function names or arguments. Key facts pinned by these snapshots:
- `ggplot2::coord_sf()` handles CRS reprojection for maps; `theme_bw()`/`theme_classic()` baselines.
- `sf::st_as_sf(coords = c("decimalLongitude", "decimalLatitude"), crs = 4326)` converts DwC points.
- `rnaturalearth::ne_countries(scale = "medium", returnclass = "sf")` is the baseline basemap; high-res needs rnaturalearthhires (NOT packaged on conda-forge — use `maps::map()` fallback instead).
- `arrow::read_parquet()` / `open_dataset()` read crosscheck + obis-gbif-fetch parquet outputs.
- `scico::scale_fill_scico()` palettes (vik,roma,batlow) are perceptually uniform & CVD-safe; viridis as alternative for all-realm consistency.
