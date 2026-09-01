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
