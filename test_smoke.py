#!/usr/bin/env python3
"""Top-level structural smoke tests for the occurrence-crosscheck meta-skill (v2.0.0).

Mirrors the bioinfo-skill-creator battle-test style: router wiring, sub-skill
frontmatter coherence, contract presence, env isolation. 18 checks.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip("'\"")
    return fm


def main() -> int:
    print("== Router ==")
    master = ROOT / "SKILL.md"
    text = master.read_text() if master.exists() else ""
    fm = frontmatter(master) if master.exists() else {}
    check("master SKILL.md exists with frontmatter", bool(fm), "missing or unparsable")
    check("master name == occurrence-crosscheck", fm.get("name") == "occurrence-crosscheck", str(fm.get("name")))
    check("master version 2.0.0", fm.get("version") == "2.0.0", str(fm.get("version")))
    check("master has updated + triggers", "updated" in fm and "triggers" in fm)
    for sub, phase in (("crosscheck", "1"), ("viz", "2"), ("publish", "3")):
        check(f"master routes to {sub}/", f"{sub}/" in text and f"Phase {phase}" in text)

    print("== Sub-skill integrity ==")
    for sub in ("crosscheck", "viz", "publish"):
        sfm = frontmatter(ROOT / sub / "SKILL.md")
        check(f"{sub}/SKILL.md frontmatter (name/version/triggers)",
              bool(sfm.get("name")) and bool(sfm.get("version")) and "triggers" in str((ROOT / sub / "SKILL.md").read_text()))

    print("== Historical battle-test verdicts carried over ==")
    expected = {"crosscheck": "PASS", "viz": "PASS-WITH-WARNINGS", "publish": "PASS"}
    for sub, verdict in expected.items():
        report = ROOT / sub / "battle-test-report.md"
        ok = report.exists() and verdict in report.read_text()[:400]
        check(f"{sub}/battle-test-report.md contains {verdict}", ok)

    print("== Merge provenance ==")
    manifest_path = ROOT / "merge-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        check("merge-manifest.json lists 3 components", len(manifest.get("components", [])) == 3)
        check("merge-manifest pre-merge SHAs recorded", all(c.get("pre_merge_head") for c in manifest["components"]))
    except Exception as exc:  # noqa: BLE001
        check("merge-manifest.json parses", False, str(exc))
    bundles = Path(__file__).resolve().parents[2] / "archieved"
    check("pre-merge git bundles archived in workspace archieved/",
          bundles.exists() and len(list(bundles.glob("*.bundle"))) == 3, str(bundles))

    print("== Frozen contracts present in sub-skills ==")
    cc = ROOT / "crosscheck"
    check("crosscheck writes flagged_occurrences contract (signoff_status)",
          "signoff_status" in (cc / "crosscheck" / "crosscheck.py").read_text())
    check("crosscheck realm test harness present", (cc / "test" / "verify_battle_test.py").exists())
    pub = ROOT / "publish"
    pub_scripts = " ".join(p.read_text() for p in (pub / "scripts").glob("*.py"))
    check("publish hard gates implemented (pending + realm + WoRMS LSID)",
          all(s in pub_scripts for s in ("pending", "marine", "marinespecies.org")))
    viz = ROOT / "viz"
    check("viz realm configs present (marine/freshwater/terrestrial)",
          all((viz / "config" / f"run-config.{r}.json").exists() for r in ("marine", "freshwater", "terrestrial")))
    check("viz marine config accepts crosscheck env names (env_bio_thetao)",
          "env_bio_thetao" in (viz / "config" / "run-config.marine.json").read_text())

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())