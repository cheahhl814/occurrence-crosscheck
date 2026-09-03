"""Shared HTTP client with a per-run network call log.

Every remote GET made by any sub-skill goes through here, tagged with a
`source` (gbif|obis|worms|fishbase|bio-oracle|worldclim-chelsa). The
battle-test reads the resulting call_log.jsonl to assert which sources were
(and were not) contacted for each realm — real evidence, not code review.

User-Agent header carries the calling user's email in the standard
`Name/Version (mailto:email)` form (RFC 7231 appendix + GBIF/OBIS API
guidance) so remote services can contact the user about rate-limits,
broken queries, or attribution. `user_email` is a required constructor
arg: preflight MUST collect it from the user and write it to params.json
so every NetLog consumer reads the same value. Hard-fails at construction
if missing or malformed — no anonymous calls.

ponytail: no retry/backoff framework, add urllib3 Retry if flaky sources
show up in practice.
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
import requests

# basic RFC-5322-ish sanity: local@domain.tld, no whitespace, at least one
# dot in the domain. This is a coarse check; the email is for API
# contact/attribution, not for sending mail, so we don't need full RFC
# compliance.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
    OBIS's /v3/occurrence endpoint silently ignores any basisOfRecord query
    param (all casings/formats tried, live-verified 2026-09-03) — this filter
    is applied client-side to individual records instead. See
    obis_filtered_count() for the count-only case."""
    return (basis_of_record or "").strip().lower() in OBIS_BASIS_OF_RECORD

# OBIS returns a full page of up to this many records in one request (live-
# verified: size=10000 for a taxon with total=1130 returned all 1130 in one
# call) — used as the post-retrieval-filter cap in obis_filtered_count().
OBIS_COUNT_FILTER_CAP = 10000


def obis_filtered_count(net: "NetLog", base_url: str) -> int | None:
    """basisOfRecord-filtered OBIS occurrence count, post-retrieval (mirrors the
    fix in workflows/obis-gbif-fetch/scripts/fetch_obis.py): OBIS's total field
    has no server-side basisOfRecord filter, so this fetches a cheap size=0 raw
    total first, then — only if that's > 0 — one page of up to
    OBIS_COUNT_FILTER_CAP full records, filtered client-side via
    obis_basis_of_record_ok().
    ponytail: exact for any species whose raw (unfiltered) total is <=
    OBIS_COUNT_FILTER_CAP; an undercount above it (OBIS's /v3/occurrence has no
    documented basisOfRecord filter to paginate around instead). Upgrade path:
    offset-paginate past the cap if a report shows a suspiciously round
    near-cap count for a very common species.
    `base_url` must not already include `size`; a taxon/geometry query only.
    """
    try:
        r = net.get("obis", f"{base_url}&size=0")
        r.raise_for_status()
        raw_total = r.json().get("total")
    except Exception:
        return None
    if not raw_total:
        return raw_total  # 0 or None — nothing to fetch/filter
    try:
        r = net.get("obis", f"{base_url}&size={min(raw_total, OBIS_COUNT_FILTER_CAP)}")
        r.raise_for_status()
        return sum(1 for x in r.json().get("results", []) if obis_basis_of_record_ok(x.get("basisOfRecord")))
    except Exception:
        return None


class NetLog:
    def __init__(self, run_dir: str | Path, user_email: str, version: str = "1.0"):
        if not user_email or not _EMAIL_RE.match(user_email):
            raise ValueError(
                f"NetLog: user_email is required and must look like an email address "
                f"(got {user_email!r}). Preflight must collect it from the user and write "
                f"it to params.json:user_email. This is GBIF/OBIS API contact-attribution "
                f"policy (https://www.gbif.org/api), not optional."
            )
        self.user_email = user_email
        self.user_agent = f"edna-crosscheck/{version} (mailto:{user_email})"
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "call_log.jsonl"

    def get(self, source: str, url: str, timeout: int = 20, **kwargs) -> requests.Response:
        assert source in ALLOWED_SOURCES, f"unknown source tag {source!r}"
        t0 = time.time()
        resp = None
        err = None
        # Always override User-Agent so callers can't accidentally strip our
        # contact-attribution header.
        kwargs.setdefault("headers", {})
        kwargs["headers"]["User-Agent"] = self.user_agent
        try:
            resp = requests.get(url, timeout=timeout, **kwargs)
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
