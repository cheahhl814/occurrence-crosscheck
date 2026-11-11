#!/usr/bin/env python3
"""Regression tests for crosscheck/lib/geo.py (v2.5.2 geodesic helpers).

Offline, stdlib-only. The v2.5.2.1 fix: ring_coords() must treat
ring_km / EARTH_R_KM as radians directly — a math.radians() wrapper shrank every
ring by a factor of pi/180 (R=2000 km became a 34.9 km circle; caught by a
pre-push sanity check before any server-side circle_wkt() query shipped).
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from lib.geo import circle_wkt, corrected_box, haversine_km, ring_coords  # noqa: E402

TENGAH_LON, TENGAH_LAT, R = 103.956811, 2.476405, 2000.0


class RingCoordsTests(unittest.TestCase):
    def test_ring_radius_is_ring_km(self):
        """Every ring point must sit at ~ring_km geodesic distance from the site."""
        for ring in (2000.0, 50.0):
            pts = ring_coords(TENGAH_LON, TENGAH_LAT, ring, n=64)
            ds = [haversine_km(lon, lat, TENGAH_LON, TENGAH_LAT) for lon, lat in pts[:-1]]
            self.assertTrue(all(abs(d - ring) < ring * 0.01 for d in ds),
                            f"ring={ring}: dist range [{min(ds):.2f}, {max(ds):.2f}]")
            self.assertEqual(pts[0], pts[-1])  # closed ring

    def test_ring_on_equator_cardinal_points(self):
        pts = ring_coords(0.0, 0.0, 2000.0, n=4)
        deg = math.degrees(2000.0 / 6371.0)  # ~17.98 deg
        latitudes = [lat for _, lat in pts[:4]]
        self.assertTrue(any(abs(lat - deg) < 0.1 for lat in latitudes))

    def test_antimeridian_returns_none(self):
        self.assertIsNone(circle_wkt(179.99, 0.1, 500))
        self.assertIsNone(circle_wkt(-179.99, -0.1, 500))

    def test_normal_circle_returns_polygon(self):
        wkt = circle_wkt(TENGAH_LON, TENGAH_LAT, 2000)
        self.assertTrue(wkt.startswith("POLYGON(("))
        self.assertTrue(wkt.endswith("))"))
        self.assertLessEqual(max(float(tok.split()[0]) for tok in
                                 "".join(wkt[9:-2].split("),(")).split(",")), 180.0)

    def test_corrected_box_covers_ring(self):
        lon_min, lat_min, lon_max, lat_max = corrected_box(TENGAH_LON, TENGAH_LAT, R)
        pts = ring_coords(TENGAH_LON, TENGAH_LAT, R)
        lons = [lon for lon, _ in pts]; lats = [lat for _, lat in pts]
        self.assertLessEqual(lon_min, min(lons))
        self.assertGreaterEqual(lon_max, max(lons))
        self.assertLessEqual(lat_min, min(lats))
        self.assertGreaterEqual(lat_max, max(lats))
        # cos(lat)-correction: lon pad (in km) ~ lat pad; a plain R/111 box would not cover
        lon_pad_km = haversine_km(TENGAH_LON, TENGAH_LAT, lon_max, TENGAH_LAT)
        lat_pad_km = haversine_km(TENGAH_LON, TENGAH_LAT, TENGAH_LON, lat_max)
        self.assertAlmostEqual(lon_pad_km, R, delta=R * 0.02)
        self.assertAlmostEqual(lat_pad_km, R, delta=R * 0.02)


class HaversineTests(unittest.TestCase):
    def test_one_degree_equator(self):
        self.assertAlmostEqual(haversine_km(0, 0, 1, 0), 111.19, delta=0.1)

    def test_same_point_zero(self):
        self.assertEqual(haversine_km(5, 5, 5, 5), 0.0)


if __name__ == "__main__":
    unittest.main()
