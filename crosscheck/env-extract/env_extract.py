#!/usr/bin/env python3
"""env-extract: realm-routed environmental enrichment.

Never issues per-point remote calls. Downloads ONE bbox-subset NetCDF per
unique (layer, scenario, depth-class) for marine (Bio-ORACLE v3 ERDDAP
griddap — server does the bbox slice), or ONE global raster archive per
unique layer for freshwater/terrestrial (WorldClim, cached under
env-extract/.cache/ since WorldClim has no server-side bbox subsetting),
then extracts values for every point LOCALLY (netCDF4 / rasterio).

marine: surface vs benthic layer chosen from the FishBase depth range
already resolved for that taxon (trait_depth_max_m > BENTHIC_THRESHOLD_M ->
benthic/"depthmax" dataset variant, else surface/"depthsurf"). No depth
info -> surface (documented default, see preflight.md).

Usage: python3 env_extract.py <points.csv with scientificName,decimalLatitude,decimalLongitude,trait_depth_max_m>
                               <routing.json> <params.json> <work_dir>
Writes: <work_dir>/env_values.csv (scientificName+lat+lon key -> env_* columns + env_layer_class)
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / ".cache"
BENTHIC_THRESHOLD_M = 30.0

ERDDAP_BASE = "https://erddap.bio-oracle.org/erddap/griddap"
WORLDCLIM_ELEV_ZIP = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_elev.zip"
WORLDCLIM_BIO_ZIP = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
BIO_VAR_INDEX = {"bio1": 1, "bio12": 12}  # WorldClim bioclim variable numbering


def bio_oracle_dataset_id(layer: str, scenario: str, depth_class: str) -> str:
    scen = "baseline" if scenario == "present" else scenario
    years = "2000_2019" if scen == "baseline" else "2020_2100"
    return f"{layer}_{scen}_{years}_{depth_class}"


def fetch_bio_oracle_bbox(net: NetLog, dataset_id: str, var: str, bbox: list[float]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{dataset_id}__{var}__{'_'.join(str(round(b, 2)) for b in bbox)}.nc"
    if out.exists():
        return out
    min_lon, min_lat, max_lon, max_lat = bbox
    url = (
        f"{ERDDAP_BASE}/{dataset_id}.nc?{var}_mean"
        f"%5B(2010-01-01T00:00:00Z)%5D"
        f"%5B({min_lat}):({max_lat})%5D%5B({min_lon}):({max_lon})%5D"
    )
    r = net.get("bio-oracle", url, timeout=60)
    if r.status_code != 200:
        print(f"env-extract: WARNING bio-oracle fetch failed {r.status_code} for {dataset_id}", file=sys.stderr)
        return None
    out.write_bytes(r.content)
    return out


def nearest_value_netcdf(nc_path: Path, var: str, lat: float, lon: float) -> float | None:
    import netCDF4 as nc
    ds = nc.Dataset(nc_path)
    try:
        lats = ds.variables["latitude"][:]
        lons = ds.variables["longitude"][:]
        vals = ds.variables[f"{var}_mean"][:]
        import numpy as np
        li = int(np.abs(lats - lat).argmin())
        lj = int(np.abs(lons - lon).argmin())
        v = vals[0, li, lj] if vals.ndim == 3 else vals[li, lj]
        import numpy.ma as ma
        if ma.is_masked(v):
            return None
        v = float(v)
        fill = getattr(ds.variables[f"{var}_mean"], "_FillValue", None)
        if fill is not None and abs(v - float(fill)) < 1e-3:
            return None
        return v
    finally:
        ds.close()


def fetch_worldclim_archive(net: NetLog, url: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / Path(url).name
    if dest.exists():
        return dest
    r = net.get("worldclim-chelsa", url, timeout=300, stream=True)
    r.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def extract_worldclim_tif(zip_path: Path, member_glob: str) -> Path:
    import zipfile
    extract_dir = CACHE_DIR / (zip_path.stem + "_extracted")
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if member_glob in n]
        if not names:
            return None
        target = extract_dir / names[0]
        if not target.exists():
            z.extract(names[0], extract_dir)
        return target


def nearest_value_raster(tif_path: Path, lat: float, lon: float) -> float | None:
    import rasterio
    with rasterio.open(tif_path) as ds:
        row, col = ds.index(lon, lat)
        try:
            v = ds.read(1)[row, col]
        except IndexError:
            return None
        v = float(v)
        nodata = ds.nodata
        if nodata is not None and abs(v - nodata) < 1e-3:
            return None
        return v


def main() -> None:
    points_csv, routing_path, params_path, work_dir = sys.argv[1:5]
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(routing_path) as f:
        routing = json.load(f)
    with open(params_path) as f:
        params = json.load(f)

    # Read user_email from work_dir/params.json (preflight writes it there).


    params_p = work_dir / "params.json"


    if not params_p.exists():


        print("FAIL: " + str(params_p) + " missing — run preflight first.", file=sys.stderr)


        sys.exit(2)


    user_email = json.loads(params_p.read_text())["user_email"]


    net = NetLog(work_dir, user_email=user_email)
    bbox = params["bbox"]
    scenario = params.get("env_scenario", "present")
    prefix = routing["env_column_prefix"]

    with open(points_csv) as f:
        points = list(csv.DictReader(f))

    out_rows = []
    if routing["realm"] == "marine":
        layers = params["env_layers"]["bio_oracle"]
        cache_nc: dict[tuple, Path] = {}
        for p in points:
            depth = p.get("trait_depth_max_m") or ""
            depth_class = "depthmax" if (depth and float(depth) > BENTHIC_THRESHOLD_M) else "depthsurf"
            env_vals = {}
            for layer in layers:
                key = (layer, scenario, depth_class)
                if key not in cache_nc:
                    dsid = bio_oracle_dataset_id(layer, scenario, depth_class)
                    cache_nc[key] = fetch_bio_oracle_bbox(net, dsid, layer, bbox)
                nc_path = cache_nc[key]
                v = nearest_value_netcdf(nc_path, layer, float(p["decimalLatitude"]), float(p["decimalLongitude"])) if nc_path else None
                env_vals[f"{prefix}{layer}"] = v
            out_rows.append({
                "scientificName": p["scientificName"], "decimalLatitude": p["decimalLatitude"],
                "decimalLongitude": p["decimalLongitude"], "env_layer_class": "benthic" if depth_class == "depthmax" else "surface",
                **env_vals,
            })
    else:
        layers = params["env_layers"]["worldclim_chelsa"]
        tif_cache: dict[str, Path] = {}
        elev_zip = bio_zip = None
        if "elev" in layers:
            elev_zip = fetch_worldclim_archive(net, WORLDCLIM_ELEV_ZIP)
            tif_cache["elev"] = extract_worldclim_tif(elev_zip, "elev")
        bio_needed = [l for l in layers if l in BIO_VAR_INDEX]
        if bio_needed:
            bio_zip = fetch_worldclim_archive(net, WORLDCLIM_BIO_ZIP)
            for layer in bio_needed:
                tif_cache[layer] = extract_worldclim_tif(bio_zip, f"bio_{BIO_VAR_INDEX[layer]}.tif")
        for p in points:
            env_vals = {}
            for layer in layers:
                tif = tif_cache.get(layer)
                v = nearest_value_raster(tif, float(p["decimalLatitude"]), float(p["decimalLongitude"])) if tif else None
                env_vals[f"{prefix}{layer}"] = v
            out_rows.append({
                "scientificName": p["scientificName"], "decimalLatitude": p["decimalLatitude"],
                "decimalLongitude": p["decimalLongitude"], "env_layer_class": "elev-bioclim",
                **env_vals,
            })

    out_csv = work_dir / "env_values.csv"
    fieldnames = list(out_rows[0].keys()) if out_rows else ["scientificName", "decimalLatitude", "decimalLongitude", "env_layer_class"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"env-extract: realm={routing['realm']} source={routing['env_source']} {len(out_rows)} points -> {out_csv}")


if __name__ == "__main__":
    main()
