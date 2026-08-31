# Bio-ORACLE v3 via ERDDAP — offline reference (marine env layers)

Source: https://bio-oracle.org/ , ERDDAP instance https://erddap.bio-oracle.org/erddap/ . Endpoint
listing and griddap query format verified live 2026-08-31 (this sandbox has direct network access to
`erddap.bio-oracle.org`).

## Dataset ID naming convention (verified via `/erddap/tabledap/allDatasets.json`)

```
<variable>_<scenario>_<years>_<depth-class>
```

- `<variable>`: e.g. `thetao` (ocean temperature), `so` (salinity)
- `<scenario>`: `baseline` (maps to this skill's `env_scenario="present"`) or `ssp119`/`ssp126`/`ssp245`/
  `ssp370`/`ssp460`/`ssp585` (CMIP6)
- `<years>`: `2000_2019` for baseline, `2020_2100` for SSP scenarios
- `<depth-class>`: `depthsurf` (surface — used when the taxon's FishBase depth range implies a
  surface-dwelling species), `depthmean`, `depthmax` (used by this skill as the "benthic" proxy when
  `trait_depth_max_m > 30`), `depthmin`

Confirmed real dataset IDs (subset): `thetao_baseline_2000_2019_depthsurf`,
`thetao_baseline_2000_2019_depthmax`, `thetao_baseline_2000_2019_depthmean`,
`thetao_baseline_2000_2019_depthmin`, plus one `_ssp1xx..ssp585` variant of each for CMIP6 scenarios.

## Griddap bbox NetCDF subset query (server-side bbox slice — the "download once" mechanism)

```
GET https://erddap.bio-oracle.org/erddap/griddap/<dataset_id>.nc?<var>_mean[(TIME)][(minLat):(maxLat)][(minLon):(maxLon)]
```

Verified live (2026-08-31):

```
GET https://erddap.bio-oracle.org/erddap/griddap/thetao_baseline_2000_2019_depthsurf.nc?thetao_mean[(2010-01-01T00:00:00Z)][(1.5):(6.5)][(99.5):(104.5)]
-> 200 OK, 86976 bytes, valid NetCDF (netCDF4-readable)
```

Note: the `depthsurf` dataset variant has only `time, latitude, longitude` dimensions (no separate depth
axis) — the depth selection is baked into which *dataset* you query (`depthsurf` vs `depthmax` vs
`depthmean`), not a query dimension. `.das` metadata confirms variables `thetao_max`, `thetao_ltmax`,
`thetao_mean`, etc. — this skill uses the `_mean` variant of each requested layer name.

## This skill's usage (`env-extract/env_extract.py`)

One griddap request per unique `(layer, scenario, depth_class)` tuple for the run's bbox — never
per-point. Local nearest-neighbor lookup against the returned NetCDF grid for every point via
`netCDF4`. `_FillValue` (-9999.9) cells are treated as "no value" (e.g., an inland/on-land coordinate
queried against a marine layer) rather than a spurious numeric value.
