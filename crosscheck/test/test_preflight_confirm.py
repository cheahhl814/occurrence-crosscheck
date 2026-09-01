#!/usr/bin/env python3
"""--require-confirm backstop tests (SP-10): auto buffer on a degenerate
extent must FAIL when confirmation is required, a user-declared buffer must
pass and print the confirmation line, and omitting the flag must reproduce
today's WARN-only behavior. Offline."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PREFLIGHT = SKILL / "preflight" / "preflight.py"

# All rows share one coordinate -> degenerate extent (span 0.0 < 0.05 threshold)
DEGENERATE_CSV = """scientificName,decimalLatitude,decimalLongitude,eventDate
Gadus morhua,2.9857056,101.2587923,2026-06-01
Salmo salar,2.9857056,101.2587923,2026-06-01
"""


class RequireConfirmTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.csv = self.tmp / "input.csv"
        self.csv.write_text(DEGENERATE_CSV)
        self.out = self.tmp / "params.json"

    def run_pf(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(PREFLIGHT), str(self.csv), "marine", "12S", str(self.out), *args],
            capture_output=True, text=True)

    def test_auto_degenerate_with_require_confirm_fails(self):
        r = self.run_pf("--require-confirm")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL auto buffer on degenerate extent requires user confirmation (SP-10)", r.stderr)

    def test_user_buffer_with_require_confirm_goes(self):
        r = self.run_pf("--require-confirm", "--buffer-km", "150")
        self.assertEqual(r.returncode, 0)
        self.assertIn("preflight: SP-10 confirmed (buffer=user-km)", r.stdout)
        self.assertIn("preflight: GO", r.stdout)

    def test_no_flag_keeps_warn_only_behavior(self):
        r = self.run_pf()
        self.assertEqual(r.returncode, 0)
        self.assertIn("preflight: WARNING auto buffer", r.stderr)
        self.assertIn("preflight: GO", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
