#!/usr/bin/env python3
"""Unit tests for habitat_iucn (pure functions; no network)."""
import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "crosscheck"))
from habitat_iucn import read_species, read_candidates  # noqa: E402


class TestReaders(unittest.TestCase):
    def test_read_species_txt(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, newline="") as fh:
            fh.write("Lutjanus johnii\n\nHilsa kelee\n")
        names = read_species(Path(fh.name))
        self.assertEqual(names, ["Lutjanus johnii", "Hilsa kelee"])

    def test_read_candidates_dedup(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as fh:
            fh.write("scientificName,candidate_of,candidate_rank\n"
                     "Sillago maculata,Sillago,1\n"
                     "Sillago sihama,Sillago,2\n"
                     "Sillago maculata,Sillago,1\n")
        ts = read_candidates(Path(fh.name))
        self.assertEqual(len(ts), 2)
        self.assertEqual(ts[0]["candidate_of"], "Sillago")


if __name__ == "__main__":
    unittest.main(verbosity=2)
