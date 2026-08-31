# WorldClim 2.1 / CHELSA — offline reference (freshwater + terrestrial env layers)

Source: https://www.worldclim.org/data/worldclim21.html , direct download host
https://geodata.ucdavis.edu/climate/worldclim/2_1/ . CHELSA (https://chelsa-climate.org/) documented as
an available higher-resolution alternative but not wired up in v1 (WorldClim is the default; see
preflight.md). Verified live 2026-08-31.

## Direct HTTPS raster downloads (no client SDK, no live API — plain files)

```
https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_elev.zip     (elevation, single band, ~1.3 MB)
https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip      (all 19 bioclim vars bundled, ~50 MB)
```

Verified live (2026-08-31): both return `200 OK`, `Accept-Ranges: bytes`, correct `Content-Length`.
There is no per-variable individual-file download at this resolution (`wc2.1_10m_bio_1.tif` standalone
-> `404`); the 19 bioclim variables ship as one zip and must be downloaded together, then the needed
member(s) extracted locally.

## Variable naming inside the bioclim zip

`wc2.1_10m_bio_<N>.tif`, N = 1..19 (standard WorldClim/CHELSA bioclim numbering, e.g. `bio_1` = annual
mean temperature, `bio_12` = annual precipitation). This skill's `params.json.env_layers.worldclim_chelsa`
uses the short form `bio1`, `bio12`, `elev`; `env_extract.py` maps `bio1`->N=1, `bio12`->N=12 via
`BIO_VAR_INDEX`.

## This skill's usage (`env-extract/env_extract.py`)

ONE download of `wc2.1_10m_elev.zip` and ONE download of `wc2.1_10m_bio.zip` per skill install (cached
under `env-extract/.cache/`, shared across every run/realm — WorldClim has no server-side bbox
subsetting, unlike Bio-ORACLE's ERDDAP griddap, so the "download once" unit here is the whole global
raster archive, not a bbox slice). Needed members (`elev.tif`, `bio_1.tif`, `bio_12.tif`) are extracted
from the zip locally, then every point is looked up via `rasterio` nearest-pixel indexing — never a
remote call per point.

## realm mapping

`freshwater` and `terrestrial` both route to this source (PLAN §2 scope table); `env_layer_class` is
recorded as `elev-bioclim` for both (vs. `surface`/`benthic` for marine).
