#!/usr/bin/env python3
"""Unit tests for the species_images fetcher (pure functions; no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crosscheck"))
from species_images import license_flag, read_species, _slug  # noqa: E402


class TestLicenseFlag(unittest.TestCase):
    def test_cc0(self):
        self.assertEqual(license_flag("http://creativecommons.org/publicdomain/zero/1.0/"), "cc-best")

    def test_cc_by(self):
        for v in ("2.5", "3.0", "4.0"):
            self.assertEqual(license_flag(f"http://creativecommons.org/licenses/by/{v}/"), "cc-best")

    def test_cc_by_sa(self):
        self.assertEqual(license_flag("http://creativecommons.org/licenses/by-sa/4.0/"), "cc-best")

    def test_by_nc_family(self):
        for terms in ("by-nc", "by-nc-sa", "by-nc-nd"):
            self.assertEqual(license_flag(f"http://creativecommons.org/licenses/{terms}/4.0/"), "by-nc")

    def test_all_rights_reserved(self):
        self.assertEqual(license_flag(""), "flag-no-license")
        self.assertEqual(license_flag("all rights reserved"), "flag-all-rights-reserved")
        self.assertEqual(license_flag(None), "flag-no-license")

    def test_inat_codes(self):
        self.assertEqual(license_flag("", "cc0"), "cc-best")
        self.assertEqual(license_flag("", "cc-by"), "cc-best")
        self.assertEqual(license_flag("", "cc-by-nc"), "by-nc")
        self.assertEqual(license_flag("", ""), "flag-no-license")
        self.assertEqual(license_flag("", "some junk"), "flag-no-license")

    def test_unknown_string(self):
        self.assertEqual(license_flag("http://example.com/whatever"), "flag-no-license")


class TestSpeciesList(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(_slug("Lutjanus johnii"), "Lutjanus_johnii")

    def test_ambiguous_detection(self):
        # temp csv built inline
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            f.write("scientificName\nLutjanus johnii\nSillago sp. 2 SS-2021\nDanio rerio\n")
            path = f.name
        names, amb = read_species(Path(path))
        self.assertEqual(names, ["Lutjanus johnii", "Sillago sp. 2 SS-2021", "Danio rerio"])
        self.assertEqual(amb, {"Sillago sp. 2 SS-2021"})


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCandidates(unittest.TestCase):
    def test_load_candidates(self):
        import tempfile
        from species_images import load_candidates
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            f.write("genus,candidate_species,rank,n_records_in_buffer\n"
                    "Sillago,Sillago maculata Quoy & Gaimard, 1824,1,3\n"
                    "Sillago,Sillago sihama (Forsskål, 1775),2,3\n"
                    ",,0,0\n")
            path = f.filename
        ts = load_candidates(Path(path))
        self.assertEqual(len(ts), 2)
        self.assertEqual(ts[0]["scientificName"], "Sillago maculata")
        self.assertEqual(ts[0]["candidate_of"], "Sillago")
        self.assertEqual(ts[1]["candidate_display"], "Sillago sihama (Forsskål, 1775)")
