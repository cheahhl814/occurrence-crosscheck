#!/usr/bin/env python3
"""occurrence-publish — sub-skill 4: validate (GBIF Data Validator + OBIS structural checks).

GBIF leg:
  1. Online (default): POST https://api.gbif.org/v1/validation (multipart file=@zip),
     poll GET https://api.gbif.org/v1/validation?key=...  (docs-corpus/gbif-data-validator/).
     401/403 -> auth_required; network error -> unreachable. Both fall back to (2).
  2. Local structural fallback (documented, always recorded locally): zip/meta.xml/eml.xml
     parse, location existence, field index bounds, term URIs, rowType vocabulary.

OBIS leg: LOCAL structural checks only (never a live IPT push): eventID integrity,
parentEventID resolution, single root, occurrence/link resolution, coordinate ranges,
depth ordering, WoRMS LSID format QC.

--offline forces fallback. Writes *_gbif_validation.json / *_obis_validation.json.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
import dwca_core as d  # noqa: E402
from dwca_core import DWCA_NS  # noqa: E402

VALIDATOR_URL = "https://api.gbif.org/v1/validation"
POLL_URL_TMPL = "https://api.gbif.org/v1/validation?key={key}"
POLL_TRIES, POLL_SLEEP = 12, 5
WORMS_LSID_RE = r"^urn:lsid:marinespecies\.org:taxname:\d+$"

DWCS_NS = {"": "http://rs.tdwg.org/dwc/text/"}


def _localname(tag):
    return tag.rsplit("}", 1)[-1]


def _q(tag):
    """dwc/text-namespace-qualified tag for ElementTree finds."""
    return "{%s}%s" % (DWCA_NS, tag)


def _text_rows(content: bytes):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8")), delimiter="\t"))


def local_structural_checks(zip_path: Path):
    """Returns (issues, files) — issues are {field, level, message, row:None}."""
    issues, files = [], {}
    with zipfile.ZipFile(zip_path, "r") as z:
        names = set(z.namelist())
        if "meta.xml" not in names:
            issues.append({"field": "meta.xml", "level": "error",
                           "message": "meta.xml missing from archive", "row": None})
            return issues, files
        if "eml.xml" not in names:
            issues.append({"field": "eml.xml", "level": "error",
                           "message": "eml.xml missing from archive", "row": None})
            return issues, files
        try:
            meta_root = ET.fromstring(z.read("meta.xml"))
        except ET.ParseError as e:
            issues.append({"field": "meta.xml", "level": "error",
                           "message": f"meta.xml parse error: {e}", "row": None})
            return issues, files
        try:
            eml_root = ET.fromstring(z.read("eml.xml"))
            title = None
            for el in eml_root.iter():
                if _localname(el.tag) == "title":
                    title = el
                    break
            if title is None or not (title.text or "").strip():
                issues.append({"field": "eml.xml", "level": "error",
                               "message": "eml.xml has empty <dataset><title>", "row": None})
        except ET.ParseError as e:
            issues.append({"field": "eml.xml", "level": "error",
                           "message": f"eml.xml parse error: {e}", "row": None})

        def spec_of(el, is_core):
            loc = el.find(_q("files") + "/" + _q("location"))
            location = loc.text if loc is not None else None
            if not location or location not in names:
                issues.append({"field": "meta.xml", "level": "error",
                               "message": f"rowType {el.get('rowType')}: location "
                                          f"{location!r} missing from zip", "row": None})
                return None
            header_len = None
            content = z.read(location)
            files[location] = content
            first = content.split(b"\n")[0].decode("utf-8")
            header_len = len(first.split("\t"))
            for f in el.findall(_q("field")):
                idx_s = f.get("index")
                if idx_s is None or not idx_s.isdigit() or int(idx_s) >= header_len:
                    issues.append({"field": "meta.xml", "level": "error",
                                   "message": f"field index {idx_s!r} out of range "
                                              f"(header has {header_len} cols in {location})",
                                   "row": None})
                term = f.get("term", "")
                if not term.startswith("http://") and not term.startswith("https://"):
                    issues.append({"field": "meta.xml", "level": "error",
                                   "message": f"term {term!r} is not a fully-qualified URI",
                                   "row": None})
            return content

        core = meta_root.find(_q("core"))
        exts = meta_root.findall(_q("extension"))
        if core is None:
            issues.append({"field": "meta.xml", "level": "error",
                           "message": "no <core> element", "row": None})
            return issues, files
        if core.get("rowType") not in d.KNOWN_ROWTYPES:
            issues.append({"field": "meta.xml", "level": "error",
                           "message": f"core rowType {core.get('rowType')!r} unknown",
                           "row": None})
        core_content = spec_of(core, is_core=True)
        for ext in exts:
            if ext.get("rowType") not in d.KNOWN_ROWTYPES:
                issues.append({"field": "meta.xml", "level": "warning",
                               "message": f"extension rowType {ext.get('rowType')!r} unknown",
                               "row": None})
            spec_of(ext, is_core=False)
        # core id non-empty on every row
        if core_content:
            rows = _text_rows(core_content)
            id_col = list(rows[0].keys())[0] if rows else None
            for n, r in enumerate(rows, start=2):
                if not r.get(id_col, "").strip():
                    issues.append({"field": id_col, "level": "error",
                                   "message": f"empty core id in row {n}", "row": n})
    return issues, files


def gbif_online(zip_path: Path):
    """Returns dict {online_status, report} — never raises."""
    out = {"online_status": "skipped", "report": None}
    try:
        import requests
    except ImportError:
        out["online_status"] = "requests_unavailable"
        return out
    try:
        with open(zip_path, "rb") as fh:
            resp = requests.post(VALIDATOR_URL, files={"file": fh}, timeout=120)
    except Exception as e:  # network error
        out["online_status"] = f"unreachable: {type(e).__name__}"
        return out
    if resp.status_code in (401, 403):
        out["online_status"] = f"auth_required (HTTP {resp.status_code} — anonymous " \
                               f"submission denied; endpoint exists)"
        return out
    if resp.status_code != 200 and resp.status_code != 201:
        out["online_status"] = f"unexpected_status_{resp.status_code}"
        return out
    try:
        body = resp.json()
    except Exception:
        out["online_status"] = "non_json_response"
        return out
    key = body.get("key") or body.get("datasetKey")
    if not key:
        out["online_status"] = "no_validation_key_in_response"
        out["report"] = body
        return out
    for _ in range(POLL_TRIES):
        try:
            pr = requests.get(POLL_URL_TMPL.format(key=key), timeout=60)
        except Exception as e:
            out["online_status"] = f"poll_unreachable: {type(e).__name__}"
            return out
        if pr.status_code == 200:
            try:
                pj = pr.json()
            except Exception:
                out["online_status"] = "poll_non_json"
                return out
            state = pj.get("status", pj.get("state", ""))
            if state and state not in ("RUNNING", "PENDING", "SUBMITTED", "PREPARING"):
                out["online_status"] = "online"
                out["report"] = pj
                return out
        time.sleep(POLL_SLEEP)
    out["online_status"] = "poll_timeout"
    return out


def obis_local_checks(zip_path: Path):
    """Local-only OBIS Event-Core structural checks; never a live IPT push."""
    issues = []
    with zipfile.ZipFile(zip_path, "r") as z:
        meta_root = ET.fromstring(z.read("meta.xml"))
        files = {}
        for f_el in meta_root.iter():
            loc = f_el.find(_q("files") + "/" + _q("location")) if _localname(f_el.tag) in ("core", "extension") else None
            if loc is not None and loc.text:
                files[loc.text] = _text_rows(z.read(loc.text))

        core_file = meta_root.find(_q("core") + "/" + _q("files") + "/" + _q("location"))
        events = files[core_file.text]
        coreid_el = next(meta_root.find(_q("core")).iter(_q("id")))
        id_col_idx = int(coreid_el.get("index"))
        header = list(events[0].keys()) if events else []
        id_name = header[id_col_idx] if header else "eventID"

        event_ids = [e[id_name] for e in events]
        if len(event_ids) != len(set(event_ids)):
            issues.append({"field": "eventID", "level": "error",
                           "message": "duplicate eventID in event core", "row": None})
        id_set = set(event_ids)
        parents = [e.get("parentEventID", "") for e in events]
        nonroot = [p for p in parents if p]
        if nonroot and not all(p in id_set for p in nonroot):
            for n, p in enumerate(parents, start=2):
                if p and p not in id_set:
                    issues.append({"field": "parentEventID", "level": "error",
                                   "message": f"parentEventID {p!r} not in eventID set", "row": n})
        roots = [e for e in events if not e.get("parentEventID")]
        if len(roots) != 1:
            issues.append({"field": "eventID", "level": "error",
                           "message": f"expected exactly 1 root event, found {len(roots)}",
                           "row": None})

        # coordinates sanity on any event carrying them
        for n, e in enumerate(events, start=2):
            lat, lon = e.get("decimalLatitude"), e.get("decimalLongitude")
            if lat and lon:
                try:
                    lat_f, lon_f = float(lat), float(lon)
                    if not (-90 <= lat_f <= 90):
                        issues.append({"field": "decimalLatitude", "level": "error",
                                       "message": f"latitude {lat_f} out of range", "row": n})
                    if not (-180 <= lon_f <= 180):
                        issues.append({"field": "decimalLongitude", "level": "error",
                                       "message": f"longitude {lon_f} out of range", "row": n})
                except ValueError:
                    issues.append({"field": "decimalLatitude", "level": "error",
                                   "message": f"non-numeric coordinate ({lat}, {lon})", "row": n})
            mn, mx = e.get("minimumDepthInMeters"), e.get("maximumDepthInMeters")
            if mn and mx:
                try:
                    if float(mn) > float(mx):
                        issues.append({"field": "minimumDepthInMeters", "level": "error",
                                       "message": f"minDepth {mn} > maxDepth {mx}", "row": n})
                except ValueError:
                    pass

        # linkage: occurrence eventIDs resolve; DNA occurrenceIDs resolve; WoRMS LSID QC
        occ_loc = meta_root.find(_q("extension") + "/" + _q("files") + "/" + _q("location"))
        occurrences = files[occ_loc.text] if occ_loc is not None else []
        occ_occ_ids = set(o.get("occurrenceID", "") for o in occurrences)
        for n, o in enumerate(occurrences, start=2):
            if o.get("eventID") and o["eventID"] not in id_set:
                issues.append({"field": "eventID", "level": "error",
                               "message": f"occurrence eventID {o['eventID']!r} unresolved",
                               "row": n})
            if not o.get("occurrenceID", "").strip():
                issues.append({"field": "occurrenceID", "level": "error",
                               "message": "occurrence row missing occurrenceID", "row": n})
        import re as _re
        for n, o in enumerate(occurrences, start=2):
            snid = o.get("scientificNameID", "")
            if snid and not _re.match(WORMS_LSID_RE, snid):
                issues.append({"field": "scientificNameID", "level": "error",
                               "message": f"non-WoRMS LSID: {snid!r}", "row": n})
            if not snid:
                issues.append({"field": "scientificNameID", "level": "error",
                               "message": "missing scientificNameID (WoRMS LSID required)", "row": n})
        # DNA-derived occurrenceIDs resolve
        dna_rows = []
        for ext in meta_root.findall(_q("extension")):
            rt = ext.get("rowType", "")
            if rt.endswith("DNADerivedData") or rt.endswith("ExtendedMeasurementOrFact"):
                loc = ext.find(_q("files") + "/" + _q("location"))
                if loc is not None:
                    coreid_idx = int(ext.find(_q("coreid")).get("index"))
                    for n, r in enumerate(files[loc.text], start=2):
                        link_col = list(r.keys())[coreid_idx]
                        if rt.endswith("DNADerivedData"):
                            dna_rows.append(r)
                        if link_col == "occurrenceID" and r[link_col] not in occ_occ_ids:
                            issues.append({"field": "occurrenceID", "level": "error",
                                           "message": f"extension occurrenceID {r[link_col]!r} "
                                                      f"unresolved in occurrence ext", "row": n})
        for n, rr in enumerate(dna_rows, start=2):
            if not (rr.get("occurrenceID") or "").strip():
                issues.append({"field": "occurrenceID", "level": "error",
                               "message": "DNA-derived row missing occurrenceID", "row": n})
    return issues


def verdict_of(issues):
    levels = [i["level"] for i in issues]
    if "error" in levels:
        return "NO-GO"
    if "warning" in levels:
        return "GO-WITH-WARNINGS"
    return "GO"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--work", default=".")
    ap.add_argument("--offline", action="store_true",
                    help="skip the online GBIF validator; local structural checks only")
    args = ap.parse_args()
    run_dir, work = Path(args.run_dir), Path(args.work)
    work = work / "work" if work.name != "work" else work
    overall = "GO"

    # ---------------- GBIF leg ----------------
    gbif_zips = sorted(run_dir.glob("*_gbif_dwca.zip"))
    if gbif_zips:
        zip_path = gbif_zips[0]
        local_issues, _ = local_structural_checks(zip_path)
        online = gbif_online(zip_path) if not args.offline else {"online_status": "skipped_offline"}
        mode = "online" if online["online_status"] == "online" else (
            "local_only_offline" if args.offline else "local_fallback")
        rep = {
            "leg": "gbif", "zip": str(zip_path),
            "validation_mode": mode,
            "online_status": online["online_status"],
            "online_report": online.get("report"),
            "validator_url": VALIDATOR_URL,
            "fallback_note": ("Online GBIF Data Validator used (POST %s). If fallback: "
                              "local structural checks only — interpretation-level checks "
                              "(taxonomy match, coordinate interpretation) NOT covered."
                              % VALIDATOR_URL),
            "local_checks": local_issues,
            "verdict": verdict_of(local_issues if mode != "online" else local_issues),
        }
        (run_dir / f"{zip_path.stem.replace('_gbif_dwca', '')}_gbif_validation.json") \
            .write_text(json.dumps(rep, indent=2, default=str))
        print(f"[validate] GBIF leg: mode={mode} online_status={online['online_status']} "
              f"verdict={rep['verdict']}")
        if rep["verdict"] == "NO-GO":
            overall = "NO-GO"

    # ---------------- OBIS leg ----------------
    obis_zips = sorted(run_dir.glob("*_obis_dwca.zip"))
    if obis_zips:
        zip_path = obis_zips[0]
        issues = obis_local_checks(zip_path)
        rep = {"leg": "obis", "zip": str(zip_path),
               "validation_mode": "local_structural_only",
               "note": "OBIS-side checks are local structural only (never a live IPT push), "
                       "per docs-corpus/obis-dna-data/.",
               "issues": issues, "verdict": verdict_of(issues)}
        (run_dir / f"{zip_path.stem.replace('_obis_dwca', '')}_obis_validation.json") \
            .write_text(json.dumps(rep, indent=2))
        print(f"[validate] OBIS leg: mode=local_structural_only verdict={rep['verdict']} "
              f"issues={len(issues)}")
        if rep["verdict"] == "NO-GO":
            overall = "NO-GO"

    if not gbif_zips and not obis_zips:
        print("[validate] NO-GO: no DwC-A zips found in run dir — run a publish sub-skill first.")
        return 2

    print(f"[validate] overall verdict: {overall}")
    return 0 if overall != "NO-GO" else 2


if __name__ == "__main__":
    sys.exit(main())