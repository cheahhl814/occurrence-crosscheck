"""Shared HTTP client with a per-run network call log.

Every remote GET made by any sub-skill goes through here, tagged with a
`source` (gbif|obis|worms|fishbase|bio-oracle|worldclim-chelsa). The
battle-test reads the resulting call_log.jsonl to assert which sources were
(and were not) contacted for each realm — real evidence, not code review.

ponytail: no retry/backoff framework, add urllib3 Retry if flaky sources
show up in practice.
"""
from __future__ import annotations
import json
import time
import os
from pathlib import Path
import requests

ALLOWED_SOURCES = {"gbif", "obis", "worms", "fishbase", "bio-oracle", "worldclim-chelsa",
                   # species-images fetcher (v2.3.0): iNaturalist is realm-agnostic
                   # (GBIF-spine tier: used for licensed portraits, not occurrence data)
                   "inaturalist"}

# basisOfRecord allow-list for GBIF/OBIS occurrence queries — excludes museum
# PreservedSpecimen/FossilSpecimen/LivingSpecimen records, whose coordinates
# often reflect a collecting institution, an old type-locality, or a captive
# source rather than an actual in-situ detection. HUMAN_OBSERVATION,
# MACHINE_OBSERVATION and OBSERVATION are real in-situ sightings; MATERIAL_SAMPLE
# is kept because that's the basisOfRecord this project's own eDNA data is
# published under (see publish/ sub-skill).
GBIF_BASIS_OF_RECORD = ["HUMAN_OBSERVATION", "MACHINE_OBSERVATION", "MATERIAL_SAMPLE", "OBSERVATION"]
# GBIF DwC term equivalents, lowercased, for client-side filtering of OBIS records.
OBIS_BASIS_OF_RECORD = {"humanobservation", "machineobservation", "materialsample", "occurrence"}


def gbif_basis_of_record_qs() -> str:
    """URL query-string fragment restricting a GBIF occurrence/search call to
    GBIF_BASIS_OF_RECORD (GBIF ORs repeated basisOfRecord params; verified live)."""
    return "".join(f"&basisOfRecord={v}" for v in GBIF_BASIS_OF_RECORD)


def obis_basis_of_record_ok(basis_of_record: str | None) -> bool:
    """True if an OBIS record's basisOfRecord passes OBIS_BASIS_OF_RECORD.
    ponytail: OBIS's /v3/occurrence endpoint silently ignores any basisOfRecord
    query param (all casings/formats tried, live-verified 2026-09-03) — ergo
    this filter is applied client-side to individual records, not server-side.
    It therefore only applies where full records are fetched (context_records.py);
    OBIS's count-only endpoints (size=0/1, total field) can't be filtered this
    way without turning an exact count into a capped sample, so those stay
    unfiltered by basisOfRecord — see occurrence_lookup.py / range_lookup.py."""
    return (basis_of_record or "").strip().lower() in OBIS_BASIS_OF_RECORD


class NetLog:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "call_log.jsonl"

    def get(self, source: str, url: str, timeout: int = 20, **kwargs) -> requests.Response:
        assert source in ALLOWED_SOURCES, f"unknown source tag {source!r}"
        t0 = time.time()
        resp = None
        err = None
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "edna-crosscheck/1.0"}, **kwargs)
        except Exception as e:  # noqa: BLE001 - we want to log the failure and re-raise
            err = str(e)
            raise
        finally:
            record = {
                "ts": time.time(),
                "source": source,
                "url": url,
                "status": resp.status_code if resp is not None else None,
                "elapsed_s": round(time.time() - t0, 3),
                "error": err,
            }
            with open(self.log_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        return resp

    def sources_called(self) -> set[str]:
        if not self.log_path.exists():
            return set()
        out = set()
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.add(json.loads(line)["source"])
        return out
