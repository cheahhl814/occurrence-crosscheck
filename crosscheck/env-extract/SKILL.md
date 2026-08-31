---
name: edna-crosscheck-env-extract
description: Realm-routed environmental enrichment — Bio-ORACLE v3/ERDDAP for marine (surface/benthic chosen from FishBase depth), WorldClim/CHELSA for freshwater/terrestrial. Always bulk-downloads once per unique layer key, then extracts point values locally — never a per-point remote call.
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "edna-crosscheck env extract"
  - "bio-oracle extract"
  - "worldclim bioclim extract"
---

# env-extract/edna-crosscheck-env-extract

## Inputs
- `points_with_depth.csv` — occurrence points + `trait_depth_max_m` (joined in from fishbase-traits
  output by the orchestrator script, `bin/run-crosscheck.sh`, before this sub-skill runs).
- `routing.json`, `params.json` (bbox, `env_layers`, `env_scenario`).

## Outputs
- `env_values.csv` — one row per `(scientificName, decimalLatitude, decimalLongitude)` with `env_*`
  columns (prefix from `routing.env_column_prefix`) and `env_layer_class`.

## Procedure
```bash
python3 env_extract.py <points_with_depth.csv> <routing.json> <params.json> <work_dir>
```
marine: one ERDDAP griddap NetCDF bbox request per `(layer, scenario, depth_class)` tuple (server-side
bbox slice — see `docs-corpus/bio-oracle/README.md`), local `netCDF4` nearest-neighbor lookup per point.
freshwater/terrestrial: one global raster archive download per unique layer, cached under
`env-extract/.cache/` (persists across runs/realms — WorldClim has no server-side bbox subsetting), local
`rasterio` nearest-pixel lookup per point.

## Ask-user stop points

**SP1 — surface vs benthic depth-class threshold.** Evidence: PLAN §4 says the choice must come "from
the FishBase depth range already resolved for that taxon" but doesn't pin an exact meters threshold.
Recommend: `trait_depth_max_m > 30m -> benthic (depthmax dataset)`, else surface — a conservative cut
that keeps shallow reef/pelagic fish on the surface layer. Decision (pinned as an open parameter,
resolved here): `BENTHIC_THRESHOLD_M = 30.0`, documented in `env_extract.py`; taxa with no resolved depth
default to surface.

**SP2 — WorldClim resolution.** Evidence: WorldClim 2.1 ships at 10m/5m/2.5m/30s arc-resolutions; higher
resolution = much larger downloads. Recommend: 10 arc-minute (`wc2.1_10m_*`) — coarsest, smallest
download, adequate for a first-pass envelope check (not a fine-scale SDM). Decision (pinned default):
10m resolution; a future SP could expose this as a `params.json` field if finer resolution is needed.

**SP3 — CHELSA vs WorldClim.** Evidence: task pin names both as acceptable; CHELSA offers higher-quality
mountain/complex-terrain climatology but WorldClim's direct-HTTPS zip download is simpler to wire up with
no auth/registration step. Recommend: WorldClim as the v1 default. Decision (pinned, "WorldClim/CHELSA" —
either acceptable): WorldClim implemented; CHELSA left as a documented drop-in alternative (same
raster-extraction code path, different source URL) rather than built now.

## Signature library

| stderr / evidence pattern | likely cause | fix |
|---|---|---|
| `WARNING bio-oracle fetch failed 400 for <dataset_id>` | dataset_id doesn't exist for that variable/scenario/depth-class combo (Bio-ORACLE doesn't publish every combination) | check `docs-corpus/bio-oracle/README.md`'s confirmed dataset-ID list, or query `https://erddap.bio-oracle.org/erddap/tabledap/allDatasets.json?datasetID=~"<var>.*"` before wiring a new layer into params.json |
| `env_*` column is null for every marine point even inside the bbox | `_FillValue` (-9999.9) returned for every cell — coordinates likely on land relative to Bio-ORACLE's ocean mask | this is expected/correct behavior (see `crosscheck.py`'s ENVELOPE_VIOLATION check), not a bug — but if EVERY point nulls out, double check bbox lat/lon order wasn't swapped |
| `env-extract/.cache/wc2.1_10m_bio.zip.part` left on disk after a crash | download interrupted mid-stream | delete the `.part` file and re-run; `fetch_worldclim_archive` only renames `.part` -> final name after a complete download, so a stale `.part` never gets treated as cached |
