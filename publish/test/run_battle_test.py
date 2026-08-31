#!/usr/bin/env python3
"""occurrence-publish battle-test (dry-run, full pipeline, synthetic fixture).

Scenarios (per pinned battle-test requirements):
  S1 happy-marine      : signed-off flagged rows -> gbif + obis zips + validations GO
  S2 pending-block     : signoff_status=pending -> GATE-A blocks preflight AND publish legs
  S3 realm-gate        : realm=freshwater -> GATE-B: obis-publish refuses, no zip
  S4 worms-missing     : rows without AphiaID -> GATE-C hard-reject in obis leg, obis_rejections.json
  S5 gbif-structural   : GBIF zip structurally valid (meta.xml correct, EML present+parsed)

Writes per-scenario logs to test/output/ and a summary JSON to test/output/battle_summary.json.
Exit 0 iff all scenario assertions pass.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
OUTROOT = SKILL_ROOT / "test" / "output"
sys.path.insert(0, str(SCRIPTS))

DWCA_NS = "http://rs.tdwg.org/dwc/text/"


def _q(tag):
    return "{%s}%s" % (DWCA_NS, tag)


RESULTS = []


def run_scenario(name, realm, signoff, missing_aphia, expect_preflight_ok,
                 expect_gbif, expect_obis, expect_gate_c=False):
    run_dir = OUTROOT / f"run_{name}"
    if run_dir.exists():
        import shutil
        shutil.rmtree(run_dir)
    subprocess.run([sys.executable, str(SKILL_ROOT / "test" / "make_fixture.py"),
                    "--out", str(run_dir), "--realm", realm, "--signoff", signoff,
                    "--missing-aphia", str(missing_aphia)], check=True,
                   capture_output=True, text=True)
    log = {"scenario": name}

    def run(script, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), "--run-dir", str(run_dir),
             "--work", str(SKILL_ROOT), *extra],
            capture_output=True, text=True, cwd=str(SKILL_ROOT))

    # ---------------- sub-skill 1: preflight ----------------
    pre = run("op_preflight.py")
    log["preflight_rc"] = pre.returncode
    log["preflight_tail"] = pre.stdout.strip().splitlines()[-3:]
    ok = True
    if expect_preflight_ok and pre.returncode != 0:
        ok = False; log["fail"] = f"preflight unexpectedly failed: {pre.stderr[-400:]}"
    if not expect_preflight_ok and pre.returncode == 0:
        ok = False; log["fail"] = "HARD GATE (a) FAILED: preflight allowed pending rows"

    # ---------------- sub-skill 2: gbif-publish ----------------
    if pre.returncode == 0:
        g = run("gbif_publish.py")
        log["gbif_rc"] = g.returncode
        gbif_zip = run_dir / "SYNTH001_gbif_dwca.zip"
        if expect_gbif and (g.returncode != 0 or not gbif_zip.is_file()):
            ok = False; log["fail"] = f"gbif-publish failed: {g.stdout[-200:]} {g.stderr[-400:]}"
        if not expect_gbif and gbif_zip.is_file():
            ok = False; log["fail"] = "gbif zip produced where it should not be"
    else:
        gbif_zip = run_dir / "SYNTH001_gbif_dwca.zip"

    # ---------------- sub-skill 3: obis-publish ----------------
    obis_zip = run_dir / "SYNTH001_obis_dwca.zip"
    if pre.returncode == 0:
        extra = ["--allow-incertae-sedis"] if name == "S1_happy_marine" else []
        o = run("obis_publish.py", *extra)
        log["obis_rc"] = o.returncode
        log["obis_tail"] = (o.stdout + o.stderr).strip().splitlines()[-2:]
        if expect_obis and (o.returncode != 0 or not obis_zip.is_file()):
            ok = False; log["fail"] = f"obis-publish failed: {o.stdout[-300:]} {o.stderr[-400:]}"
        if not expect_obis and obis_zip.is_file():
            ok = False; log["fail"] = "HARD GATE (b) FAILED: obis zip produced for non-marine realm"
        if expect_gate_c and o.returncode == 0:
            ok = False; log["fail"] = "HARD GATE (c) FAILED: obis-publish accepted rows without WoRMS LSID"
        rej = SKILL_ROOT / "work" / "obis_rejections.json"
        if expect_gate_c and not rej.is_file():
            ok = False; log["fail"] = "GATE-C: obis_rejections.json missing"
        if expect_gate_c and rej.is_file():
            body = json.loads(rej.read_text())
            log["gate_c_refused_records"] = body.get("refused_records")
            if body.get("refused_records", 0) < 1:
                ok = False; log["fail"] = "GATE-C report lists no refused records"
    if not pre.returncode == 0:
        # gates must leave no publishable state behind
        if obis_zip.exists() or gbif_zip.exists():
            ok = False; log["fail"] = "blocked run still produced a zip"

    # ---------------- sub-skill 4 + structural checks (S1 / happy path only) ----------------
    if expect_gbif and expect_obis and pre.returncode == 0 and gbif_zip.is_file():
        v = run("validate.py", "--offline")
        log["validate_rc"] = v.returncode
        val = run_dir / "SYNTH001_gbif_validation.json"
        if not val.is_file():
            ok = False; log["fail"] = "validate did not write _gbif_validation.json"
        obis_val = run_dir / "SYNTH001_obis_validation.json"
        if not obis_val.is_file():
            ok = False; log["fail"] = "validate did not write _obis_validation.json"
        # ---- S5 structural assertions INSIDE the zip
        with zipfile.ZipFile(gbif_zip) as z:
            names = set(z.namelist())
            if not {"meta.xml", "eml.xml"} <= names:
                ok = False; log["fail"] = f"gbif zip missing meta/eml (has {sorted(names)})"
            else:
                meta_root = ET.fromstring(z.read("meta.xml"))
                core = meta_root.find(_q("core"))
                if core is None or not core.get("rowType", "").endswith("Occurrence"):
                    ok = False; log["fail"] = "gbif meta.xml core rowType wrong"
                meta_xml = z.read("meta.xml").decode()
                if 'metadata="eml.xml"' not in meta_xml:
                    ok = False; log["fail"] = "meta.xml does not declare metadata=eml.xml"
                eml_root = ET.fromstring(z.read("eml.xml"))
                title = next((el for el in eml_root.iter()
                              if el.tag.rsplit("}", 1)[-1] == "title"), None)
                if title is None or "eDNA" not in (title.text or ""):
                    ok = False; log["fail"] = "EML title missing/odd"
        if obis_zip.is_file():
            with zipfile.ZipFile(obis_zip) as z:
                meta_root = ET.fromstring(z.read("meta.xml"))
                core = meta_root.find(_q("core"))
                if not core.get("rowType", "").endswith("Event"):
                    ok = False; log["fail"] = "obis meta.xml core rowType is not Event"
                exts = {e.get("rowType", "").rsplit("/", 1)[-1]
                        for e in meta_root.findall(_q("extension"))}
                if not {"Occurrence", "DNADerivedData"} <= exts:
                    ok = False; log["fail"] = f"obis extensions missing: {exts}"
                # hierarchy assertions: survey->station->sample->seq
                loc = meta_root.find(_q("core") + "/" + _q("files") + "/" + _q("location")).text
                events = list(csv.DictReader(io.StringIO(z.read(loc).decode()), delimiter="\t"))
                types = [e.get("type") for e in events]
                for need in ("survey/cruise", "station", "sample", "sequencing event"):
                    if need not in types:
                        ok = False; log["fail"] = f"event hierarchy missing {need}"
                eids = {e["eventID"] for e in events}
                for e in events:
                    if e["parentEventID"] and e["parentEventID"] not in eids:
                        ok = False; log["fail"] = f"parent unresolved: {e['parentEventID']}"
        obv = json.loads(obis_val.read_text()) if obis_val.is_file() else {}
        if obv.get("verdict") not in ("GO", "GO-WITH-WARNINGS"):
            ok = False; log["fail"] = f"obis validation verdict {obv.get('verdict')}: {obv.get('issues')}"

    status = "PASS" if ok else "FAIL"
    log["status"] = status
    RESULTS.append(log)
    print(f"  [{status}] {name}")
    if not ok:
        print(f"         -> {log.get('fail')}")
    return ok


def main() -> int:
    OUTROOT.mkdir(parents=True, exist_ok=True)
    ok = True
    print("[battle-test] occurrence-publish v1.0.0 — synthetic fixture dry-run")
    ok &= run_scenario("S1_happy_marine", "marine", "approved", 0,
                       expect_preflight_ok=True, expect_gbif=True, expect_obis=True)
    ok &= run_scenario("S2_pending_block", "marine", "pending", 0,
                       expect_preflight_ok=False, expect_gbif=False, expect_obis=False)
    ok &= run_scenario("S3_realm_gate_freshwater", "freshwater", "approved", 0,
                       expect_preflight_ok=True, expect_gbif=True, expect_obis=False)
    ok &= run_scenario("S4_worms_missing", "marine", "approved", 2,
                       expect_preflight_ok=True, expect_gbif=True, expect_obis=False,
                       expect_gate_c=True)
    summary = {"tool": "occurrence-publish battle-test", "scenarios": RESULTS,
               "fixture": "synthetic (test/make_fixture.py) per PLAN §11.8 rule 4",
               "overall": "PASS" if ok else "FAIL"}
    (OUTROOT / "battle_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[battle-test] overall: {'PASS' if ok else 'FAIL'}  (summary: "
          f"{OUTROOT / 'battle_summary.json'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())