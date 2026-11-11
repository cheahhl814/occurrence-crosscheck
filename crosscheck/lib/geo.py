"""Geodesic ring helpers (v2.5.2) — true-distance semantics for the concordance ring.

The pre-v2.5.2 ring was an axis-aligned bounding box (input extent ± R/111° on BOTH
axes, no cos(lat) correction): box-corner points were up to ~sqrt(2)·R km from the
site while still counting as "in-ring", and the km→deg conversion drifted at higher
latitudes. These helpers implement true geodesic semantics:

  * ring_coords(lon0, lat0, ring_km, n) — n points on a great circle of radius
    ring_km around the site (haversine / spherical earth, R=6371 km).
  * circle_wkt(lon0, lat0, ring_km, n) — those points as a WKT POLYGON that
    GBIF/OBIS accept via their `geometry` parameter, so occurrence COUNTS are
    server-side filtered to within ring_km. If the circle crosses the antimeridian,
    returns None (callers fall back to the lon-corrected box and should log it).
  * haversine_km(lon1, lat1, lon2, lat2) — great-circle distance, R=6371 km.

GBIF & OBIS both accept `geometry=<POLYGON WKT>` and filter occurrences with a
geo_shape predicate; polygon approximation error for n=64 is < 0.1% of the radius.
"""
from __future__ import annotations
import math

EARTH_R_KM = 6371.0


def ring_coords(lon0: float, lat0: float, ring_km: float, n: int = 64) -> list[tuple[float, float]]:
    """Points on a great circle of radius ring_km around (lat0, lon0); closes the ring."""
    d = math.radians(ring_km / EARTH_R_KM)
    lat0r, lon0r = math.radians(lat0), math.radians(lon0)
    pts = []
    for k in range(n):
        bearing = 2 * math.pi * k / n
        lat = math.asin(math.sin(lat0r) * math.cos(d) +
                        math.cos(lat0r) * math.sin(d) * math.cos(bearing))
        lng = lon0r + math.atan2(math.sin(bearing) * math.sin(d) * math.cos(lat0r),
                                 math.cos(d) - math.sin(lat0r) * math.sin(lat))
        pts.append((math.degrees(lng), math.degrees(lat)))  # (lon, lat)
    pts.append(pts[0])  # close the ring
    return pts


def circle_wkt(lon0: float, lat0: float, ring_km: float, n: int = 64) -> str | None:
    """WKT POLYGON of the ring_km geodesic circle, or None if it crosses ±180°.

    Antimeridian policy: rather than emit longitudes outside [-180, 180] (GBIF/OBIS
    validate the range) or guess at MULTIPOLYGON support, callers fall back to the
    lon-corrected bounding box. Only relevant for sites within ring_km of ±180°.
    """
    pts = ring_coords(lon0, lat0, ring_km, n)
    lons = [p[0] for p in pts]
    if max(lons) > 180.0 or min(lons) < -180.0:
        return None
    return ("POLYGON((" + ",".join(f"{lon:.6f} {lat:.6f}" for lon, lat in pts) + "))")


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km on the sphere (R = 6371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlt = math.radians(lat2 - lat1)
    dln = math.radians(lon2 - lon1)
    a = math.sin(dlt / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dln / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def corrected_box(lon0: float, lat0: float, ring_km: float) -> list[float]:
    """Bounding box that fully covers a ring_km geodesic circle around the site.

    Latitude uses 111 km/deg; longitude is cos(lat)-corrected so a site away from
    the equator still gets the full east-west circle inside the box.
    """
    lat_pad = ring_km / 111.0
    coslat = max(0.05, math.cos(math.radians(lat0)))
    lon_pad = ring_km / (111.0 * coslat)
    return [lon0 - lon_pad, lat0 - lat_pad, lon0 + lon_pad, lat0 + lat_pad]
