# skill-built.md — occurrence-publish v1.0.0 build artifact

**Built:** 2026-08-31 · **Phase:** 2 of 4 (bioinfo-skill-creator evidence chain)
**Inputs:** `preflight.md` (GO) + `params.json`
**Verdict:** BUILD COMPLETE — all structural smoke tests pass (22/22), battle-test PASS (4/4 scenarios).

## File inventory (sha256 prefix · path)

```
94eadf7b6de8  bin/skill-update-check.py
43f304be4bd0  docs-corpus/dna-derived-data-extension/README.md
5816ade05fbd  docs-corpus/dwca-profile/metaxml-sample.md
e4a30f6f21b2  docs-corpus/dwca-profile/README.md
9f9e002e86b1  docs-corpus/ednabridge-conv/README.md
55fcbd24fa1c  docs-corpus/eml-2/README.md
706212797c0e  docs-corpus/gbif-data-validator/README.md
3648427a340b  docs-corpus/obis-dna-data/README.md
96577b30c342  gbif-publish/gbif-publish/SKILL.md
dea3b425fd03  .gitignore
72e6b004df37  obis-publish/obis-publish/SKILL.md
65cfecc9fc3f  params.json
b5f56895885e  pixi.toml
1e0080639d60  preflight.md
26114106af32  preflight/preflight-publish/SKILL.md
56c9ce5e91d1  README.md
06eb2c154ad2  scripts/dwca_core.py
cc6470fa323f  scripts/gbif_publish.py
9f8a3189419b  scripts/obis_publish.py
96288f11dac5  scripts/op_preflight.py
b5c967444da3  scripts/validate.py
078615991216  SKILL.md
fc3c9fd1b6dd  test/make_fixture.py
d5a233434901  test/run_battle_test.py
1834beced343  test_smoke.py
f9b0b7d83685  validate/validate-dwca/SKILL.md
```

(Runtime artifacts under `work/`, `test/output/`, and `docs-corpus/.fingerprints/` are gitignored
per `.gitignore`.)

## Notes on the build

- **Templates:** the master `SKILL.md`, README, pixi.toml, and the 4 sub-skill SKILL.md files
  follow the bioinfo-skill-creator conventions (router SKILL, §Inputs/Outputs contracts,
  §Ask-user stop points with Evidence+Recommend+Options, §Signature library ≥3 entries).
  SPs were resolved from the pinned task decisions (see `preflight.md §4`); no file was blocked.
- **Docs-corpus:** 6 tool directories, each with a populated README (≥1500 chars, source URLs,
  verbatim-captured API probing results where relevant):
  `dwca-profile` (+`metaxml-sample.md`), `eml-2`, `dna-derived-data-extension`,
  `obis-dna-data` (https://manual.obis.org/dna_data.html captured during build),
  `gbif-data-validator` (endpoint probed live: POST /v1/validation → 403 anonymous),
  `ednabridge-conv` (reference only).
- **DwC-A writer:** `scripts/dwca_core.py` — stdlib only (`zipfile`, `xml.etree`, `csv`);
  meta.xml emitted in the `http://rs.tdwg.org/dwc/text/` namespace with default-namespace
  serialization (round-trips through namespace-aware parsers); EML 2.1.1 GBIF profile with
  required dataset/title/creator/pubDate/language/abstract/keywordSet/intellectualRights/contact.
- **Hard gates:** gate (a) in `op_preflight.py` (+ belt-and-braces re-checks in both publish
  legs); gate (b) realm refusal in `obis_publish.py`; gate (c) WoRMS LSID hard-reject writing
  `work/obis_rejections.json` with remediation hints. Validated end-to-end by the battle test.
- **No runtime eDNAbridge dependency** (smoke test #20 enforces); no live publishing calls
  (smoke test #21 enforces: only `api.gbif.org/v1/validation` POST allowed, in validate only).
- **pixi:** `pixi lock --dry-run` resolves (python ≥3.11, pandas, pyarrow, requests from
  conda-forge); all 7 tasks wired.

## Verification checklist

- [x] `python3 test_smoke.py` → **OK, 22/22**
- [x] `python3 test/run_battle_test.py` → **PASS 4/4** (S1 happy marine, S2 pending-block,
      S3 realm-gate, S4 WoRMS-missing)
- [x] Online validator probe → `auth_required (HTTP 403)` recorded, local fallback GO
- [x] `pixi lock --dry-run` → rc 0
- [x] `bin/skill-update-check.py` parses; returns `NO-ORIGIN` (informational, rc 2) after the
      local-only first commit — resolves to `LOCAL-AHEAD`/`UP-TO-DATE` once the orchestrator
      adds the origin remote and pushes
- [ ] git → first commit (orchestrator/user); push deliberately NOT performed per pinned rules
- [ ] deploy to `~/.pi/agent/skills/` deliberately NOT performed per pinned rules

## Readiness for Phase 3 (battle-test)

`battle-test/skill-battle-test` consumption is authorized: `skill-built.md` exists, structural
smoke tests green. Battle-test results are recorded in `battle-test-report.md`.