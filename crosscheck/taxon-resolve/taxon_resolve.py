#!/usr/bin/env python3
"""taxon-resolve: builds/updates the scientificName -> {gbif_taxonKey,
worms_AphiaID, fishbase_SpeCode} crosswalk cache (sqlite), keyed on
scientificName (PLAN §7 risk #1 / task pin: "sqlite or parquet cache").

Query order per task pin: WoRMS (marine only) -> GBIF -> FishBase.
acceptedScientificName defaults to the GBIF backbone name (PLAN calls GBIF
"the universal backbone"); WoRMS/FishBase only contribute their ID columns
plus ambiguity signal.

FishBase note: PLAN §4/§7 hard-orders sub-skills taxon-resolve ->
fishbase-traits -> env-extract, so fishbase-traits has not run yet when
this script executes and fishbase_pull.json does not exist. fishbase_SpecCode
is therefore left NULL here and filled in during final assembly
(crosscheck.py), which joins enriched rows against fishbase_pull.json after
fishbase-traits has produced it. This script still queries WoRMS -> GBIF ->
FishBase in that priority order for anything it CAN resolve at this point
(WoRMS, GBIF); FishBase is a same-priority-slot no-op here by construction,
not a skipped step.

Ambiguous/unresolved (multiple candidates, low-confidence fuzzy GBIF match,
or WoRMS returning >1 AphiaID) never gets auto-picked — it is written to
review_queue.csv (PLAN §11.5) with candidates and left for a human.

A missing AphiaID is NOT an error for freshwater/terrestrial (PLAN §7 risk
#8) — those realms don't even query WoRMS (see realm-router), so the column
is simply NULL by construction, never treated as unresolved taxonomy.

Usage: python3 taxon_resolve.py <names_file> <routing.json> <work_dir>
Writes: <work_dir>/crosswalk_cache.sqlite, <work_dir>/review_queue.csv
"""
from __future__ import annotations
import csv
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

GBIF_MATCH = "https://api.gbif.org/v1/species/match"
WORMS_MATCH = "https://www.marinespecies.org/rest/AphiaRecordsByMatchNames"

SCHEMA = """
CREATE TABLE IF NOT EXISTS crosswalk (
  scientificName TEXT PRIMARY KEY,
  acceptedScientificName TEXT,
  gbif_taxonKey INTEGER,
  gbif_matchType TEXT,
  gbif_confidence INTEGER,
  worms_AphiaID INTEGER,
  worms_status TEXT,
  fishbase_SpecCode INTEGER,
  taxon_match_status TEXT,
  gbif_candidates TEXT,
  worms_candidates TEXT,
  fishbase_candidates TEXT
);
"""


def gbif_match(net: NetLog, name: str) -> dict:
    url = f"{GBIF_MATCH}?name={quote(name)}&verbose=true"
    r = net.get("gbif", url)
    r.raise_for_status()
    return r.json()


def worms_match(net: NetLog, name: str) -> list:
    # AphiaRecordsByMatchNames takes an array-style query: scientificnames[]=...
    url = f"{WORMS_MATCH}?scientificnames%5B%5D={quote(name)}&marine_only=true"
    r = net.get("worms", url)
    if r.status_code == 204:
        return []
    r.raise_for_status()
    data = r.json()
    # WoRMS returns a list-of-lists (one inner list per queried name)
    return data[0] if data else []


def resolve_one(net: NetLog, name: str, routing: dict) -> dict:
    row = {
        "scientificName": name,
        "acceptedScientificName": None,
        "gbif_taxonKey": None,
        "gbif_matchType": None,
        "gbif_confidence": None,
        "worms_AphiaID": None,
        "worms_status": None,
        "fishbase_SpecCode": None,
        "taxon_match_status": "unresolved",
        "gbif_candidates": "[]",
        "worms_candidates": "[]",
        "fishbase_candidates": "[]",
    }
    ambiguous = False

    # 1. WoRMS (marine-only, per realm-router)
    if routing.get("call_worms"):
        try:
            worms_hits = worms_match(net, name)
        except Exception:
            worms_hits = []
        if len(worms_hits) == 1:
            row["worms_AphiaID"] = worms_hits[0].get("AphiaID")
            row["worms_status"] = worms_hits[0].get("status")
        elif len(worms_hits) > 1:
            ambiguous = True
            row["worms_candidates"] = json.dumps(
                [{"AphiaID": h.get("AphiaID"), "scientificname": h.get("scientificname"), "status": h.get("status")} for h in worms_hits]
            )
        # 0 hits: expected/normal for a marine query with no WoRMS record — not ambiguous.

    # 2. GBIF (universal, always queried)
    try:
        gbif_res = gbif_match(net, name)
    except Exception:
        gbif_res = {}
    match_type = gbif_res.get("matchType", "NONE")
    if match_type in ("EXACT",):
        row["gbif_taxonKey"] = gbif_res.get("usageKey")
        row["gbif_matchType"] = match_type
        row["gbif_confidence"] = gbif_res.get("confidence")
        row["acceptedScientificName"] = gbif_res.get("species") or gbif_res.get("scientificName")
    elif match_type == "FUZZY" and gbif_res.get("confidence", 0) >= 90:
        row["gbif_taxonKey"] = gbif_res.get("usageKey")
        row["gbif_matchType"] = match_type
        row["gbif_confidence"] = gbif_res.get("confidence")
        row["acceptedScientificName"] = gbif_res.get("species") or gbif_res.get("scientificName")
    elif match_type in ("FUZZY", "HIGHERRANK"):
        ambiguous = True
        row["gbif_candidates"] = json.dumps([{"usageKey": gbif_res.get("usageKey"), "scientificName": gbif_res.get("scientificName"),
                                                "matchType": match_type, "confidence": gbif_res.get("confidence")}])
        if match_type == "HIGHERRANK":
            row["taxon_match_status"] = "genus_only"
    # NONE: leave unresolved, no candidates to list.

    # 3. FishBase — deferred (see module docstring); filled in during final
    # assembly once fishbase-traits has run. row["fishbase_SpecCode"] stays None here.

    # Final status
    if ambiguous:
        row["taxon_match_status"] = "ambiguous"
    elif row["taxon_match_status"] == "genus_only":
        pass
    elif row["gbif_taxonKey"] is None:
        row["taxon_match_status"] = "unresolved"
    else:
        row["taxon_match_status"] = "resolved"

    return row


def main() -> None:
    names_file, routing_path, work_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(routing_path) as f:
        routing = json.load(f)
    names = [n.strip() for n in Path(names_file).read_text().splitlines() if n.strip()]

    net = NetLog(work_dir)
    db_path = work_dir / "crosswalk_cache.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(SCHEMA)

    review_rows = []
    for name in names:
        cached = con.execute("SELECT scientificName FROM crosswalk WHERE scientificName=?", (name,)).fetchone()
        if cached:
            continue
        row = resolve_one(net, name, routing)
        con.execute(
            """INSERT OR REPLACE INTO crosswalk
               (scientificName, acceptedScientificName, gbif_taxonKey, gbif_matchType, gbif_confidence,
                worms_AphiaID, worms_status, fishbase_SpecCode, taxon_match_status,
                gbif_candidates, worms_candidates, fishbase_candidates)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["scientificName"], row["acceptedScientificName"], row["gbif_taxonKey"], row["gbif_matchType"],
                row["gbif_confidence"], row["worms_AphiaID"], row["worms_status"], row["fishbase_SpecCode"],
                row["taxon_match_status"], row["gbif_candidates"], row["worms_candidates"], row["fishbase_candidates"],
            ),
        )
        if row["taxon_match_status"] in ("ambiguous", "unresolved"):
            review_rows.append(row)
    con.commit()

    review_path = work_dir / "review_queue.csv"
    with open(review_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scientificName", "match_status", "gbif_candidates", "worms_candidates", "fishbase_candidates", "chosen", "decision_reason"])
        for row in review_rows:
            w.writerow([row["scientificName"], row["taxon_match_status"], row["gbif_candidates"],
                        row["worms_candidates"], row["fishbase_candidates"], "", ""])

    con.close()
    print(f"taxon-resolve: {len(names)} names processed, {len(review_rows)} sent to review_queue.csv -> {db_path}")


if __name__ == "__main__":
    main()
