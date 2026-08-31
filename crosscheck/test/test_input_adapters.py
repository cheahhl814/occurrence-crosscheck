#!/usr/bin/env python3
"""Smoke tests for the input-adapter modes (PLAN §4 extension, 2026-08-31).

Offline structural + unit tests (no network) — the live inverted queries are
exercised by bin/run_species.sh / bin/run_coordinates.sh against real APIs.

Usage: python3 test/test_input_adapters.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ADAPTER = SKILL / "preflight" / "input_adapters.py"


class CompileTests(unittest.TestCase):
    def test_new_modules_compile(self):
        for mod in ("preflight/input_adapters.py", "crosscheck/range_lookup.py",
                    "crosscheck/checklist_builder.py"):
            r = subprocess.run([sys.executable, "-m", "py_compile", SKILL / mod], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr.decode())

    def test_pixi_tasks_registered(self):
        toml = (SKILL / "pixi.toml").read_text()
        self.assertIn("species-list", toml)
        self.assertIn("coordinates-checklist", toml)

    def test_orchestrators_executable(self):
        self.assertTrue((SKILL / "bin/run_species.sh").stat().st_mode & 0o111)
        self.assertTrue((SKILL / "bin/run_coordinates.sh").stat().st_mode & 0o111)


class SpeciesAdapterTests(unittest.TestCase):
    def test_species_txt_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            names_file = work / "names.txt"
            names_file.write_text("Thunnus albacares\nGadus morhua\n")

            r = subprocess.run(
                [sys.executable, str(SKILL / "preflight/input_adapters.py"),
                 "species", str(names_file), "marine", "list", str(work / "w")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            names = (work / "w/names.txt").read_text().splitlines()
            self.assertEqual(names, ["Gadus morhua", "Thunnus albacares"])  # sorted + deduped
            params = json.loads((work / "w/params.json").read_text())
            self.assertEqual(params["input_mode"], "species")
            self.assertIsNone(params["bbox"])  # inverted query marker

    def test_species_csv_mode_with_fallback_cols(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            csvf = work / "species.csv"
            csvf.write_text("species\nSalmo salar\n")
            subprocess.run([sys.executable, str(SKILL / "preflight/input_adapters.py"),
                            "species", str(csvf), "freshwater", "list", str(work / "w")],
                           check=True, capture_output=True)
            self.assertEqual((work / "w/names.txt").read_text().strip(), "Salmo salar")


class CoordAdapterTests(unittest.TestCase):
    def test_coords_mode_bbox_and_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            pts = work / "points.csv"
            pts.write_text("point_id,decimalLatitude,decimalLongitude\nA,3.0,101.4\nB,3.2,101.6\n")
            subprocess.run([sys.executable, str(SKILL / "preflight/input_adapters.py"),
                            "coords", str(pts), "marine", "checklist", str(work / "w"), "0.5"],
                           check=True, capture_output=True)
            params = json.loads((work / "w/params.json").read_text())
            # 3.0..3.2, 101.4..101.6 padded by 0.5
            self.assertEqual(params["bbox"], [100.9, 2.5, 102.1, 3.7])
            self.assertEqual(params["input_mode"], "coords")
            geo = (work / "w/points_geo.csv").read_text().splitlines()
            self.assertTrue(geo[0].startswith("scientificName,"))  # env-extract contract
            self.assertIn("A", geo[1])
            self.assertTrue((work / "w/points.csv").exists())  # id-bearing for joins

    def test_missing_lat_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("lat,lon\n3.0,101.4\n")  # decimal keys absent, fallbacks exist -> actually ok
            ok = Path(tmp) / "ok.csv"
            ok.write_text("foo\n1.0\n")  # no coord columns at all -> must fail
            r = subprocess.run([sys.executable, str(SKILL / "preflight/input_adapters.py"),
                                "coords", str(ok), "marine", "checklist", str(Path(tmp) / "w")],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("FAIL", r.stderr)

    def test_realm_validation(self):
        r = subprocess.run([sys.executable, str(SKILL / "preflight/input_adapters.py"),
                            "species", "/dev/null", "space", "x", str(Path("/tmp/should-not-exist-x"))],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


class InvertedQueryStructureTests(unittest.TestCase):
    def test_range_lookup_honors_routing(self):
        src = (SKILL / "crosscheck/range_lookup.py").read_text()
        self.assertIn("call_obis", src)  # realm-routed OBIS
        self.assertNotIn("geometry=", src.split("def main")[0])  # no bbox filter anywhere

    def test_checklist_builder_filters_by_realm_flags(self):
        src = (SKILL / "crosscheck/checklist_builder.py").read_text()
        for flag in ("is_marine", "is_freshwater", "is_terrestrial", "is_brackish"):
            self.assertIn(flag, src)
        self.assertIn("results", src)  # correct OBIS checklist response key


if __name__ == "__main__":
    unittest.main(verbosity=1)