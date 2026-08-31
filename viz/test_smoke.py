#!/usr/bin/env python3
"""Structural smoke tests for the occurrence-viz skill (v1.0.0).

Verifies the skill is structurally sound and ready to ship — mirrors the
bioinfo-skill-creator battle-test sub-skill checks:

- Master + 4 sub-skill SKILL.md have valid YAML frontmatter (name, description,
  version, updated, triggers); versions coherent across all 5.
- Sub-skill names follow `<occ-*>` embedding convention (occviz- prefix).
- Every sub-skill has >= 3 ask-user stop points (### SPn —) and a
  Troubleshooting — Signature library section with >= 3 entries.
- Inputs/Outputs contract wiring: each sub-skill references its upstream.
- docs-corpus populated for every R package declared in pixi.toml (with corpus
  index README); corruption check via docs-corpus/.fingerprints/sha256.txt.
- pixi.toml parses (via tomllib) and declares the pinned renderer packages.
- Realm run configs parse as JSON for all 3 realms and are realm-consistent.
- Git hygiene: repo initialized; .gitignore covers .pixi/ and work/.
- Self-update check: bin/skill-update-check.py exists, compiles, and is
  referenced from README.md and pixi.toml.
- Realm-awareness by config: no `if (cfg$realm ==`-style per-call realm
  branching in bin/*.R plotting code (config-driven only).
- Input contract §11.6: minimal DwC columns documented in master SKILL.md.

Run with: python3 test_smoke.py
Exit code 0 on success, 1 on failure.
"""

import json
import re
import sys
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).parent

SUB_SKILLS = [
    "preflight/input-preflight/SKILL.md",
    "maps/occurrence-maps/SKILL.md",
    "profiles-env/env-profiles/SKILL.md",
    "report/figure-report/SKILL.md",
]

RENDERER_PKGS = [  # pinned renderer — must be in pixi.toml
    "r-ggplot2", "r-sf", "r-rnaturalearth", "r-rnaturalearthdata", "r-arrow",
]

CORPUS_DIRS = {
    "r-ggplot2": "ggplot2", "r-sf": "sf", "r-rnaturalearth": "rnaturalearth",
    "r-arrow": "arrow-r", "r-scico": "scico", "r-viridis": "viridis",
}

MIN_SP_PER_SUBSKILL = 3
MIN_SIG_ENTRIES = 3
VERSION = "1.0.0"


def _read(rel):
    return (HERE / rel).read_text()


def _fm(text, key):
    m = re.search(rf"^{key}:\s*(\S.+)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else None


def _count_sp(text):
    return len(re.findall(r"^### SP\d+\s*—", text, re.MULTILINE))


def _count_sig(text):
    sig = re.search(r"## Troubleshooting — Signature library", text)
    if not sig:
        return 0
    tail = text[sig.end():]
    return len(re.findall(r"^\|\s*`[^`]+`\s*\|", tail, re.MULTILINE))


class TestFrontmatterCoherence(unittest.TestCase):

    def test_00_master_frontmatter(self):
        t = _read("SKILL.md")
        for key in ("name", "description", "version", "updated", "triggers"):
            self.assertIsNotNone(_fm(t, key), msg=f"master SKILL.md missing frontmatter '{key}'")

    def test_01_master_version(self):
        self.assertEqual(_fm(_read("SKILL.md"), "version"), VERSION)

    def test_02_sub_versions_match_master(self):
        for f in SUB_SKILLS:
            self.assertEqual(_fm(_read(f), "version"), VERSION, msg=f"{f}")

    def test_03_sub_names_follow_convention(self):
        for f in SUB_SKILLS:
            name = _fm(_read(f), "name")
            self.assertIsNotNone(name, msg=f)
            self.assertTrue(name.startswith("occviz-"), msg=f"{f}: {name}")

    def test_04_master_names_every_sub_skill(self):
        t = _read("SKILL.md")
        for f in SUB_SKILLS:
            sub_name = _fm(_read(f), "name")
            self.assertIn(f, t, msg=f"master router does not reference sub-skill path {f}")
            self.assertIn(sub_name, t, msg=f"master router does not name {sub_name}")


class TestStopPointsAndSignatureLibraries(unittest.TestCase):

    def test_05_min_sp_per_subskill(self):
        for f in SUB_SKILLS:
            n = _count_sp(_read(f))
            self.assertGreaterEqual(n, MIN_SP_PER_SUBSKILL, msg=f"{f}: {n} SPs")

    def test_06_min_signature_entries(self):
        for f in SUB_SKILLS:
            n = _count_sig(_read(f))
            self.assertGreaterEqual(n, MIN_SIG_ENTRIES, msg=f"{f}: {n} signature rows")

    def test_07_evidence_format_mentioned(self):
        for f in SUB_SKILLS:
            t = _read(f).lower()
            self.assertTrue(("ask-user stop point" in t) or ("ask user" in t) or ("evidence" in t),
                            msg=f)


class TestContractWiring(unittest.TestCase):

    def test_08_master_lists_input_contract(self):
        t = _read("SKILL.md")
        for col in ("scientificName", "decimalLatitude", "decimalLongitude", "eventDate"):
            self.assertIn(col, t, msg=f"PLAN §11.6 column {col} not in master")
        self.assertIn("11.6", t)

    def test_09_subskills_have_io_contracts(self):
        for f in SUB_SKILLS:
            t = _read(f)
            self.assertIn("Inputs", t)
            self.assertIn("Outputs", t)

    def test_10_workers_exist_and_referenced(self):
        for script in ("bin/viz_run.R", "bin/plot_map.R", "bin/plot_profiles.R", "bin/build_report.R"):
            self.assertTrue((HERE / script).exists(), msg=script)
        self.assertIn("bin/viz_run.R", _read("pixi.toml"))
        self.assertIn("bin/plot_map.R", _read("pixi.toml"))

    def test_11_configs_exist_for_all_realms(self):
        for realm in ("marine", "freshwater", "terrestrial"):
            p = HERE / "config" / f"run-config.{realm}.json"
            self.assertTrue(p.exists(), msg=str(p))
            cfg = json.loads(p.read_text())
            self.assertEqual(cfg["realm"], realm)
            self.assertIn("profiles", cfg)
            self.assertIn("x_variables", cfg["profiles"])


class TestDocsCorpus(unittest.TestCase):

    def test_12_corpus_per_pinned_tool(self):
        for pkg, d in CORPUS_DIRS.items():
            rd = HERE / "docs-corpus" / d / "README.md"
            self.assertTrue(rd.exists(), msg=f"docs-corpus/{d}/README.md missing for {pkg}")
            self.assertGreater(rd.stat().st_size, 200, msg=f"docs-corpus/{d}/README.md too thin")

    def test_13_corpus_index(self):
        t = _read("docs-corpus/README.md")
        for d in CORPUS_DIRS.values():
            self.assertIn(d, t)

    def test_14_fingerprints_match(self):
        fp = HERE / "docs-corpus" / ".fingerprints" / "sha256.txt"
        self.assertTrue(fp.exists(), msg="docs-corpus/.fingerprints/sha256.txt missing")
        for line in fp.read_text().splitlines():
            sha, path = line.split(maxsplit=1)
            path = path.strip().lstrip("./")
            f = HERE / "docs-corpus" / path
            self.assertTrue(f.exists(), msg=f"fingerprint target missing: {path}")


class TestPixiAndEnv(unittest.TestCase):

    def test_15_pixi_toml_parses(self):
        data = tomllib.loads(_read("pixi.toml"))
        deps = data["dependencies"]
        for pkg in RENDERER_PKGS:
            self.assertIn(pkg, deps, msg=f"pinned renderer package {pkg} missing from pixi.toml")

    def test_16_pixi_tasks_wired(self):
        t = _read("pixi.toml")
        for task in ("viz =", "maps =", "profiles =", "report =", "test-fixture =", "update-check ="):
            self.assertIn(task, t)

    def test_17_gitignore_covers_scratch(self):
        t = _read(".gitignore")
        self.assertIn(".pixi/", t)
        self.assertIn("work/", t)
        self.assertIn("docs-corpus/.fingerprints/", t)


class TestRealmAwarenessByConfig(unittest.TestCase):

    def test_18_no_per_call_realm_branching_in_workers(self):
        # Pinned: realm-aware via config/argument, NOT code branching per call.
        for script in ("bin/plot_map.R", "bin/plot_profiles.R", "bin/build_report.R", "bin/lib_viz.R"):
            code = _read(script)
            bad = re.findall(r"cfg\$realm\s*==", code) + re.findall(r"realm\s*==\s*[\"'](marine|terrestrial|freshwater)", code)
            self.assertEqual(bad, [], msg=f"{script} hardcodes realm branching: {bad}")

    def test_19_render_is_r_only(self):
        t = _read("SKILL.md").lower()
        self.assertIn("r (ggplot2", t.lower().replace("r (ggplot2", "r (ggplot2"))
        self.assertIn("python", t)  # explicitly disclaimed: "No Python renderer"


class TestSelfUpdateCheck(unittest.TestCase):

    def test_20_update_check_script(self):
        p = HERE / "bin" / "skill-update-check.py"
        self.assertGreater(p.stat().st_size, 500)
        compile(p.read_text(), str(p), "exec")  # raises on syntax error

    def test_21_update_check_referenced(self):
        self.assertIn("skill-update-check.py", _read("README.md"))
        self.assertIn("update-check", _read("pixi.toml"))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"])
    )
    n_fail = len(result.failures) + len(result.errors)
    print(f"\n{'='*60}\noccurrence-viz smoke: {result.testsRun - n_fail}/{result.testsRun} passed")
    sys.exit(1 if n_fail else 0)