#!/usr/bin/env python3
"""Preflight buffer-zone tests (v2.1.2): buffer declared at preflight, recorded
in params.json, three modes with precedence + conflict rejection. Offline."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PREFLIGHT = SKILL / "preflight" / "preflight.py"
FIXTURE = SKILL / "test" / "fixtures" / "synthetic_asv.csv"


class BufferTests(unittest.TestCase):
    def run_pf(self, *args: str) -> tuple[int, dict, str]:
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = str(Path(tmp.name) / "params.json")
        r = subprocess.run([sys.executable, str(PREFLIGHT), str(FIXTURE), "marine", "12S", out, *args],
                           capture_output=True, text=True)
        return r.returncode, (json.loads((Path(tmp.name) / "params.json").read_text()) if r.returncode == 0 else {}), r

    def test_default_auto(self):
        rc, p, r = self.run_pf()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(p["buffer"]["mode"], "auto")
        self.assertEqual(p["buffer"]["pad_deg"], 0.25)
        # fixture extent [101.8,3.5,102.1,4.0] padded 0.25
        self.assertEqual(p["bbox"], [101.55, 3.25, 102.35, 4.25])

    def test_buffer_km_lon_corrected(self):
        rc, p, r = self.run_pf("--buffer-km", "111")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(p["buffer"]["mode"], "user-km")
        self.assertEqual(p["buffer"]["km"], 111.0)
        # at lat ~3.25 cos ~0.998 — lat pad ~1.0 deg, lon pad ~1.002
        self.assertAlmostEqual(p["buffer"]["pad_deg"], 1.002, places=2)
        self.assertEqual(p["input_extent"], [101.8, 3.5, 102.1, 4.0])

    def test_explicit_bbox_wins_and_records_extent(self):
        rc, p, r = self.run_pf("--bbox", "99.5", "1.5", "103.5", "4.5")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(p["buffer"]["mode"], "user-bbox")
        self.assertEqual(p["bbox"], [99.5, 1.5, 103.5, 4.5])
        self.assertEqual(p["input_extent"], [101.8, 3.5, 102.1, 4.0])

    def test_buffer_deg(self):
        rc, p, r = self.run_pf("--buffer-deg", "1.0")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(p["buffer"]["mode"], "user-deg")
        self.assertEqual(p["buffer"]["pad_deg"], 1.0)

    def test_conflicts_rejected(self):
        r = subprocess.run([sys.executable, str(PREFLIGHT), str(FIXTURE), "marine", "12S",
                            "/tmp/pf_conflict.json", "--buffer-km", "100", "--buffer-deg", "1"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("at most one", r.stderr)

    def test_bad_realm_rejected(self):
        r = subprocess.run([sys.executable, str(PREFLIGHT), str(FIXTURE), "space", "12S",
                            "/tmp/pf_bad2.json"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)