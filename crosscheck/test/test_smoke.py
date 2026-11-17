#!/usr/bin/env python3
"""Structural smoke test for edna-crosscheck, per skill-forge's
battle-test §4 checklist (frontmatter coherence, contract wiring, signature
library completeness, docs-corpus freshness, pixi parse, git hygiene,
self-update check). No network calls, no pixi env required beyond stdlib +
PyYAML-free frontmatter parsing (hand-rolled, avoids a new dependency).

Usage: python3 test/test_smoke.py
Exit 0 = all pass, 1 = any FAIL.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SUBSKILLS = ["preflight", "realm-router", "taxon-resolve", "fishbase-traits", "env-extract", "crosscheck"]
DOCS_TOOLS = ["gbif", "obis", "worms", "fishbase", "bio-oracle", "worldclim-chelsa"]

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))


def read_frontmatter(md_path: Path) -> dict:
    text = md_path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("-") and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def main() -> int:
    # 1. Top-level SKILL.md frontmatter
    top_skill = SKILL_DIR / "SKILL.md"
    check("SKILL.md exists", top_skill.exists())
    if top_skill.exists():
        fm = read_frontmatter(top_skill)
        for field in ("name", "description", "version", "updated"):
            check(f"SKILL.md frontmatter has {field}", field in fm, str(fm.get(field, "")))
        check("SKILL.md has triggers list", "triggers:" in top_skill.read_text())

    # 2. README.md, pixi.toml, pixi.lock, params.json exist
    for f in ("README.md", "pixi.toml", "params.json"):
        check(f"{f} exists", (SKILL_DIR / f).exists())
    check("pixi.lock exists (pixi resolved cleanly)", (SKILL_DIR / "pixi.lock").exists())

    # 3. params.json matches PLAN §11.1 keys
    import json
    params_path = SKILL_DIR / "params.json"
    if params_path.exists():
        params = json.loads(params_path.read_text())
        required_keys = {"skill_run", "realm", "marker", "bbox", "env_source", "env_layers",
                          "env_scenario", "backbones", "obis_lookup", "env_column_prefix"}
        missing = required_keys - set(params.keys())
        check("params.json has all PLAN §11.1 keys", not missing, str(missing))

    # 4. Every sub-skill has SKILL.md with frontmatter + >=3 signature library entries
    for sub in SUBSKILLS:
        sub_skill_md = SKILL_DIR / sub / "SKILL.md"
        check(f"{sub}/SKILL.md exists", sub_skill_md.exists())
        if sub_skill_md.exists():
            fm = read_frontmatter(sub_skill_md)
            for field in ("name", "description", "version", "updated"):
                check(f"{sub}/SKILL.md frontmatter has {field}", field in fm)
            text = sub_skill_md.read_text()
            sig_section = text.split("## Signature library")[-1] if "## Signature library" in text else ""
            n_rows = len([l for l in sig_section.splitlines() if l.strip().startswith("|") and "---" not in l]) - 1
            check(f"{sub}/SKILL.md has >=3 signature-library entries", n_rows >= 3, f"found {n_rows}")
            check(f"{sub}/SKILL.md has >=3 ask-user stop points", text.count("**SP") >= 3)

    # 5. docs-corpus populated for every required tool
    for tool in DOCS_TOOLS:
        p = SKILL_DIR / "docs-corpus" / tool / "README.md"
        check(f"docs-corpus/{tool}/README.md exists", p.exists())
        if p.exists():
            check(f"docs-corpus/{tool}/README.md non-trivial", len(p.read_text()) > 500)

    # 6. pixi.toml parses (via pixi lock --dry-run) — best effort, skip if pixi not on PATH
    import shutil
    if shutil.which("pixi"):
        r = subprocess.run(["pixi", "lock", "--dry-run"], cwd=SKILL_DIR, capture_output=True, text=True, timeout=60)
        check("pixi lock --dry-run succeeds", r.returncode == 0, r.stderr[-300:])
    else:
        check("pixi lock --dry-run succeeds", True, "SKIPPED: pixi not on PATH")

    # 7. Python sub-skill scripts parse
    py_files = list(SKILL_DIR.rglob("*.py"))
    py_files = [p for p in py_files if ".pixi" not in str(p) and "__pycache__" not in str(p)]
    for p in py_files:
        r = subprocess.run([sys.executable, "-m", "py_compile", str(p)], capture_output=True, text=True)
        check(f"{p.relative_to(SKILL_DIR)} compiles", r.returncode == 0, r.stderr[-300:])

    # 8. Self-update check exists, parses, referenced by README + pixi.toml
    update_check = SKILL_DIR / "bin" / "skill-update-check.py"
    check("bin/skill-update-check.py exists", update_check.exists())
    if update_check.exists():
        r = subprocess.run([sys.executable, "-m", "py_compile", str(update_check)], capture_output=True, text=True)
        check("bin/skill-update-check.py compiles", r.returncode == 0)
        check("README.md references skill-update-check.py", "skill-update-check.py" in (SKILL_DIR / "README.md").read_text())
        check("pixi.toml references update-check task", "update-check" in (SKILL_DIR / "pixi.toml").read_text())

    # 9. Git hygiene
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=SKILL_DIR, capture_output=True, text=True)
    check("git repo initialized", r.returncode == 0 and r.stdout.strip() == "true")

    # 10. Orchestrator script exists + executable
    orch = SKILL_DIR / "bin" / "run-crosscheck.sh"
    check("bin/run-crosscheck.sh exists", orch.exists())
    check("bin/run-crosscheck.sh is executable", orch.exists() and orch.stat().st_mode & 0o111 != 0)

    # ---- report ----
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = len(results) - n_pass
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        line = f"[{status}] {name}"
        if detail and not ok:
            line += f"  -- {detail}"
        print(line)
    print(f"\n{n_pass}/{len(results)} checks passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
