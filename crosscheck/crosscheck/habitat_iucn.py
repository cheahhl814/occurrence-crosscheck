#!/usr/bin/env python3
"""Habitat type + IUCN Red List manifest for the occurrence-crosscheck meta-skill.

One row per taxon (detected species, and optionally genus-narrow candidate
species) with:
  - habitat flags from WoRMS AphiaRecordsByName (isMarine/isBrackish/isFreshwater/
    isTerrestrial; ?marine_only=false so freshwater taxa resolve)
  - IUCN Red List category from GBIF /species/{usageKey}/iucnRedListCategory
    (works for all realms; includes NE)

Flags never drops: unresolvable rows keep flag:* values ("flag:woRMS-miss",
"flag:iucn-lookup-failed", "flag:unresolved") — never silent empties.
Cache-warm safe (D-audit-1 lesson): rows in an existing manifest whose taxon is
unchanged are reused untouched.

Usage:
  python3 habitat_iucn.py <species_list.csv|txt> <work_dir> [--candidates <candidate_images.csv>]
    with --candidates: candidate taxa are appended (candidate_of/rank columns kept)

Outputs: <work_dir>/habitat_iucn.csv (§11.11)
"""
from __future__ import annotations

import csv
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

GBIF_MATCH = "https://api.gbif.org/v1/species/match?name={}"
GBIF_IUCN = "https://api.gbif.org/v1/species/{}/iucnRedListCategory"
WORMS = "https://www.marinespecies.org/rest/AphiaRecordsByName/{}?marine_only=false"

IUCN_MAP = {"LC": "Least Concern", "NT": "Near Threatened", "VU": "Vulnerable",
            "EN": "Endangered", "CR": "Critically Endangered", "EX": "Extinct",
            "EW": "Extinct in the Wild", "DD": "Data Deficient", "NE": "Not Evaluated",
            "LR/nt": "Near Threatened", "LR/cd": "Conservation Dependent", "LR/lc": "Least Concern"}

FIELDS = ["scientificName", "candidate_of", "candidate_rank", "habitat", "marine", "brackish",
          "freshwater", "terrestrial", "worms_status", "iucn_code", "iucn_category",
          "flag", "fetched_at"]


def read_species(list_path: Path) -> list[str]:
    names: list[str] = []
    with open(list_path, newline="") as fh:
        if list_path.suffix.lower() == ".csv":
            for row in csv.DictReader(fh):
                for col in ("scientificName", "scientific_name", "ScientificName"):
                    if row.get(col):
                        n = re.sub(r"\s+", " ", row[col].strip())
                        if n and n not in names:
                            names.append(n)
                        break
        else:
            for line in fh:
                n = re.sub(r"\s+", " ", line.strip())
                if n and n not in names:
                    names.append(n)
    return names


def read_candidates(path: Path) -> list[dict]:
    """genus_candidates.csv rows -> candidate habitat/IUCN targets.

    genus_candidates.csv carries `candidate_species` (binomial + author citation),
    NOT `scientificName` — binomial = first two whitespace tokens (same rule as
    species_images.load_candidates). Accepts `scientificName` too for
    forward-compat with pre-filtered manifests."""
    out, seen = [], set()
    for r in csv.DictReader(open(path, newline="")):
        display = (r.get("candidate_species") or r.get("scientificName") or "").strip()
        if not display:
            continue
        binom = " ".join(display.split()[:2])
        if not binom or binom.lower() in seen:
            continue
        seen.add(binom.lower())
        out.append({"scientificName": binom, "candidate_of": r.get("genus") or r.get("candidate_of", ""),
                    "candidate_rank": r.get("rank") or r.get("candidate_rank", "")})
    return out


def iucn_of(net: NetLog, name: str) -> tuple[str, str]:
    """(code, category) or flag-prefixed error."""
    try:
        m = net.get("gbif", GBIF_MATCH.format(quote(name)), timeout=30).json()
        key = (m or {}).get("usageKey")
        if not key:
            return "", "flag:gbif-no-match"
        c = net.get("gbif", GBIF_IUCN.format(key), timeout=30).json()
        code = (c or {}).get("code") or "NE"
        return code, IUCN_MAP.get(code, code)
    except Exception as e:  # noqa: BLE001
        print(f"WARN iucn {name}: {type(e).__name__}", file=sys.stderr)
        return "", "flag:iucn-lookup-failed"


def habitat_of(net: NetLog, name: str) -> dict:
    out = {"habitat": "flag:woRMS-miss", "marine": "", "brackish": "", "freshwater": "",
           "terrestrial": "", "worms_status": ""}
    try:
        wr = net.get("worms", WORMS.format(quote(name)), timeout=30).json()
        if isinstance(wr, list) and wr:
            w = wr[0]
            rec = {"marine": w.get("isMarine"), "brackish": w.get("isBrackish"),
                   "freshwater": w.get("isFreshwater"), "terrestrial": w.get("isTerrestrial"),
                   "worms_status": w.get("status", "")}
            rec.update(rec)  # no-op clarity
            flags = [t for t in ("marine", "brackish", "freshwater", "terrestrial") if rec[t]]
            rec["habitat"] = "/".join(flags) if flags else "flag:habitat-missing"
            return rec
        return {"habitat": "flag:woRMS-miss", "marine": "", "brackish": "",
                "freshwater": "", "terrestrial": "", "worms_status": ""}
    except Exception as e:  # noqa: BLE001
        print(f"WARN worms {name}: {type(e).__name__}", file=sys.stderr)
        return {"habitat": "flag:woRMS-miss", "marine": "", "brackish": "",
                "freshwater": "", "terrestrial": "", "worms_status": ""}


def run(net: NetLog, targets: list[dict], work_dir: Path, manifest: Path) -> None:
    prev: dict[str, dict] = {}
    if manifest.exists():  # cache-warm reruns (D-audit-1 lesson)
        try:
            for r in csv.DictReader(open(manifest)):
                if r.get("habitat") and not str(r.get("habitat", "")).startswith("flag:unresolved"):
                    prev[r["scientificName"].lower()] = {k: r.get(k, "") for k in FIELDS}
        except Exception:
            prev = {}
    rows = []
    for t in targets:
        n = t["scientificName"]
        cached = prev.get(n.lower())
        if cached:
            rows.append(cached)
            continue
        rec = {k: t.get(k, "") for k in ("candidate_of", "candidate_rank")}
        rec["scientificName"] = n
        code, cat = iucn_of(net, n)
        hab = habitat_of(net, n)
        rec.update({"iucn_code": code, "iucn_category": cat}, **hab)
        rec["flag"] = ""
        if rec["habitat"].startswith("flag:") and str(rec["iucn_category"]).startswith("flag:"):
            rec["flag"] = "flag:both-sources-unresolved"
        elif rec["habitat"].startswith("flag:"):
            rec["flag"] = rec["habitat"]
        elif str(rec["iucn_category"]).startswith("flag:"):
            rec["flag"] = rec["iucn_category"]
        else:
            rec["flag"] = ""
        rec["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows.append(rec)
        time.sleep(0.05)
    with open(manifest, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        wtr.writeheader()
        for r in rows:
            wtr.writerow({k: r.get(k, "") for k in FIELDS})
    n_flag = sum(1 for r in rows if str(r.get("flag", "")).startswith("flag"))
    print(f"habitat-iucn: {len(rows)} taxa -> {manifest} ({n_flag} flagged)")


def main() -> None:
    argv = [a for a in sys.argv[1:]]
    candidates_csv = None
    if "--candidates" in argv:
        i = argv.index("--candidates")
        candidates_csv = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__)
        sys.exit(2)
    list_path, work_dir = Path(argv[0]), Path(argv[1])
    work_dir.mkdir(parents=True, exist_ok=True)
    net = NetLog(work_dir)
    targets = [{"scientificName": n, "candidate_of": "", "candidate_rank": ""}
               for n in read_species(list_path)]
    if candidates_csv:
        targets += read_candidates(candidates_csv)
    run(net, targets, work_dir, work_dir / "habitat_iucn.csv")


if __name__ == "__main__":
    main()