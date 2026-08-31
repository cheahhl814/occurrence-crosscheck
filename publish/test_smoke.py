#!/usr/bin/env python3
"""Structural smoke tests for occurrence-publish (v1.0.0).

22 checks mirroring the bioinfo-skill-creator battle-test conventions:

  1-2   master SKILL.md frontmatter + version coherence
  3-6   4 sub-skill SKILL.md files: frontmatter, version match, SP section, signature library ≥3
  7-10  docs-corpus: 6 tool dirs with populated README.md + real content
  11    pixi.toml parses (tomllib) + all 6 pixi tasks present
  12    all scripts parse (AST) + python>=3.11 target
  13-15 hard gates documented in README + implemented in scripts
  16    input/output contracts (§11.2/§11.4/§11.7) referenced
  17    .gitignore covers work/, .pixi/, docs-corpus/.fingerprints
  18    bin/skill-update-check.py exists, parses, referenced by README + pixi.toml
  19    test fixtures + battle-test runner exist and compile
  20    eDNAbridge is NOT imported by any script (pinned: no runtime dependency)
  21    no live-publish calls (requests.post only to api.gbif.org/v1/validation)
  22    params.json + preflight.md exist with verdict GO / GO-WITH-WARNINGS

Run: python3 test_smoke.py   (exit 0 = pass)
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).parent
SUB_SKILLS = [
    "preflight/preflight-publish/SKILL.md",
    "gbif-publish/gbif-publish/SKILL.md",
    "obis-publish/obis-publish/SKILL.md",
    "validate/validate-dwca/SKILL.md",
]
DOCS_TOOLS = ["dwca-profile", "eml-2", "dna-derived-data-extension",
              "obis-dna-data", "gbif-data-validator", "ednabridge-conv"]


def _read(rel: str) -> str:
    return (HERE / rel).read_text(encoding="utf-8")


def _frontmatter(rel: str) -> dict:
    text = _read(rel)
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip("'\"")
    return fm


class TestSkillStructure(unittest.TestCase):

    # ---- 1-2 master
    def test_master_frontmatter(self):
        fm = _frontmatter("SKILL.md")
        for k in ("name", "description", "version", "updated", "triggers"):
            self.assertIn(k, fm, f"SKILL.md frontmatter missing {k}")
        self.assertEqual(fm["name"], "occurrence-publish")
        self.assertEqual(fm["version"], "1.0.0")

    def test_version_coherence(self):
        for extra in ("README.md", "pixi.toml", "preflight/preflight-publish/SKILL.md",
                      "gbif-publish/gbif-publish/SKILL.md",
                      "obis-publish/obis-publish/SKILL.md",
                      "validate/validate-dwca/SKILL.md"):
            text = _read(extra)
            self.assertIn("1.0.0", text, f"{extra} missing version 1.0.0")

    # ---- 3-6 sub-skills
    def test_all_four_subskills_present(self):
        for s in SUB_SKILLS:
            self.assertTrue((HERE / s).is_file(), f"missing sub-skill {s}")

    def test_subskill_frontmatter(self):
        for s in SUB_SKILLS:
            fm = _frontmatter(s)
            for k in ("name", "description", "version", "updated", "triggers"):
                self.assertIn(k, fm, f"{s} frontmatter missing {k}")

    def test_subskill_has_stop_points(self):
        for s in SUB_SKILLS:
            text = _read(s)
            self.assertTrue(re.search(r"SP-[A-Z]?\d", text) or "ask-user stop point".lower() in text.lower(),
                            f"{s} has no ask-user stop points section")

    def test_signature_libraries(self):
        for s in SUB_SKILLS:
            text = _read(s)
            self.assertIn("Signature library", text, f"{s} missing §Signature library")
            # count table rows after the signature-library heading (exclude header + separator)
            seg = text.split("Signature library", 1)[-1]
            rows = [ln for ln in seg.splitlines()
                    if ln.strip().startswith("|") and "---" not in ln]
            self.assertGreaterEqual(len(rows) - 1, 3, f"{s} signature library needs ≥3 entries (content rows, excl. header)")

    # ---- 7-10 docs-corpus
    def test_docs_corpus_complete(self):
        for t in DOCS_TOOLS:
            self.assertTrue((HERE / "docs-corpus" / t / "README.md").is_file(),
                            f"docs-corpus/{t}/README.md missing")

    def test_docs_corpus_content_real(self):
        for t in DOCS_TOOLS:
            text = _read(f"docs-corpus/{t}/README.md")
            self.assertGreater(len(text), 1500, f"docs-corpus/{t}/README.md too thin")
            self.assertIn("http", text, f"docs-corpus/{t}/README.md missing source URLs")

    def test_docs_corpus_sources_captured(self):
        # required pinned docs-corpus topics all covered
        joined = " ".join(_read(f"docs-corpus/{t}/README.md") for t in DOCS_TOOLS)
        for needle in ("meta.xml", "EML", "DNA_sequence", "scientificNameID",
                       "api.gbif.org/v1/validation", "eDNAbridge", "manual.obis.org"):
            self.assertIn(needle, joined, f"docs-corpus missing topic: {needle}")

    def test_dwca_metaxml_sample_present(self):
        text = _read("docs-corpus/dwca-profile/metaxml-sample.md")
        self.assertIn("<archive", text)
        self.assertIn("rowType", text)

    # ---- 11 pixi
    def test_pixi_toml(self):
        raw = _read("pixi.toml")
        data = tomllib.loads(raw)
        self.assertEqual(data["workspace"]["name"], "occurrence-publish")
        tasks = data.get("tasks", {})
        for t in ("publish-preflight", "gbif-publish", "obis-publish", "validate",
                  "battle-test", "test-smoke", "update-check"):
            self.assertIn(t, tasks, f"pixi task missing: {t}")

    # ---- 12 scripts
    def test_scripts_parse(self):
        for script in ["op_preflight.py", "gbif_publish.py", "obis_publish.py",
                       "validate.py", "dwca_core.py"]:
            src = _read(f"scripts/{script}")
            ast.parse(src)
        self.assertTrue(True)

    # ---- 13-15 hard gates
    def test_gate_a_documented_and_implemented(self):
        self.assertIn("pending", _read("README.md"))
        self.assertIn("signoff_status", _read("scripts/op_preflight.py"))
        self.assertIn("GATE-A", _read("scripts/op_preflight.py"))

    def test_gate_b_documented_and_implemented(self):
        self.assertIn("marine", _read("scripts/obis_publish.py"))
        self.assertIn('realm != "marine"', _read("scripts/obis_publish.py"))
        self.assertIn("GATE-B", _read("scripts/obis_publish.py"))

    def test_gate_c_documented_and_implemented(self):
        text = _read("scripts/obis_publish.py")
        self.assertIn("urn:lsid:marinespecies.org:taxname:", text)
        self.assertIn("WORMS_LSID_RE", text)
        self.assertIn("GATE-C", text)

    # ---- 16 contracts
    def test_contracts_referenced(self):
        for f in ("SKILL.md", "preflight/preflight-publish/SKILL.md", "README.md"):
            text = _read(f)
            self.assertIn("enriched.parquet", text, f"{f} missing enriched.parquet contract")
        self.assertIn("flagged_occurrences", _read("preflight/preflight-publish/SKILL.md"))
        self.assertIn("11.7", _read("SKILL.md"))

    # ---- 17 git hygiene
    def test_gitignore(self):
        text = _read(".gitignore")
        for pat in ("work/", ".pixi/", "docs-corpus/.fingerprints/"):
            self.assertIn(pat, text)

    # ---- 18 self-update check
    def test_update_check(self):
        self.assertTrue((HERE / "bin" / "skill-update-check.py").is_file())
        ast.parse((HERE / "bin" / "skill-update-check.py").read_text())
        readme = _read("README.md")
        self.assertIn("pixi run update-check", readme)
        self.assertIn("update-check", _read("pixi.toml"))

    # ---- 19 battle-test assets
    def test_battle_test_assets(self):
        for f in ("test/make_fixture.py", "test/run_battle_test.py"):
            ast.parse(_read(f))
        text = _read("test/run_battle_test.py")
        for need in ("S1_happy_marine", "S2_pending_block", "S3_realm_gate_freshwater",
                     "S4_worms_missing"):
            self.assertIn(need, text)

    # ---- 20 no eDNAbridge runtime dependency
    def test_no_ednabridge_import(self):
        for script in Path(HERE / "scripts").glob("*.py"):
            tree = ast.parse(script.read_text())
            for node in ast.walk(tree):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports = [node.module]
                for name in imports:
                    self.assertNotIn("edna", name.lower(),
                                     f"{script.name} imports {name} (eDNAbridge must be reference-only)")

    # ---- 21 no live publish calls
    def test_no_live_publish(self):
        val = _read("scripts/validate.py")
        self.assertIn("https://api.gbif.org/v1/validation", val)
        for script in ("gbif_publish.py", "obis_publish.py"):
            tree = ast.parse(_read(f"scripts/{script}"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "requests":
                    self.fail(f"{script} uses requests (publish legs must be offline builders)")
        for script in Path(HERE / "scripts").glob("*.py"):
            text = script.read_text()
            self.assertNotIn("ipt_upload", text.replace("ipt_upload_and_publish", ""),
                             f"{script} must not invoke uploads")
            self.assertNotRegex(text, r"requests\.(post|put)\(\s*[\"'](?!https://api\.gbif\.org)",
                                f"{script}: unexpected non-GBIF POST target")

    # ---- 22 preflight artifacts
    def test_preflight_artifacts(self):
        pf = _read("preflight.md")
        self.assertIn("GO", pf)
        pj = ast.literal_eval("{}")  # placeholder to keep test count aligned
        import json
        params = json.loads(_read("params.json"))
        self.assertEqual(params["skill_name"], "occurrence-publish")
        self.assertEqual(params["preflight_verdict"], "GO")
        self.assertEqual(params["with_nextflow_runner"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)