# battle-test-report.md — occurrence-publish v1.0.0

**Date:** 2026-08-31 · **Phase:** 4 of 4 (bioinfo-skill-creator evidence chain)
**Inputs:** `skill-built.md` + `docs-corpus/` + full skill tree
**Verdict:** **PASS** (zero FAIL checks; see §Notes for 2 recorded WARN-class observations)

---

## 1. Structural smoke tests — PASS (22/22)

`python3 test_smoke.py` → `Ran 22 tests ... OK`. Coverage: master + 4 sub-skill frontmatter and
version coherence (v1.0.0), ask-user stop points present, signature libraries ≥3 entries each,
docs-corpus 6/6 tools populated with real content, pixi.toml parses with all 7 tasks,
all 5 scripts parse, HARD GATES (a)/(b)/(c) documented AND implemented, §11.2/§11.4/§11.7
contracts referenced, .gitignore hygiene, self-update check wired, battle-test assets present,
**no eDNAbridge imports** (pinned), **no live publish calls** (only `POST api.gbif.org/v1/validation`
in validate leg), `preflight.md` verdict GO + `params.json` coherent.

## 2. Execution battle-test — PASS (4/4 scenarios, synthetic fixture)

`python3 test/run_battle_test.py` → overall **PASS**; per-scenario evidence in
`test/output/battle_summary.json`.

| Scenario | Setup | Expected | Result |
|---|---|---|---|
| **S1_happy_marine** | marine fixture, flagged rows `approved` | GBIF zip + OBIS Event-Core zip built; validations GO; zip internals correct | ✅ PASS |
| **S2_pending_block** | flagged rows left `pending` (gate a) | preflight aborts GATE-A; **no zips produced** | ✅ PASS |
| **S3_realm_gate_freshwater** | manifest `realm=freshwater` (gate b) | obis-publish refuses with clear message; GBIF leg unaffected; **no obis zip** | ✅ PASS |
| **S4_worms_missing** | 2 rows without `worms_AphiaID` (gate c) | obis-publish hard-rejects, writes `work/obis_rejections.json` with remediation; **no zip produced** | ✅ PASS |

### S1 structural asserts verified inside the zips (dry-run, no network)

- **GBIF zip** (`SYNTH001_gbif_dwca.zip`): `meta.xml` present, parses, declares
  `metadata="eml.xml"`, core `rowType=http://rs.tdwg.org/dwc/terms/Occurrence`;
  `eml.xml` present, parses, has a non-empty EML title. Field terms fully-qualified URIs.
- **OBIS zip** (`SYNTH001_obis_dwca.zip`): core `rowType=...Event`; extensions
  Occurrence + DNADerivedData (+ eMoF, since `env_bio_*` columns present); event hierarchy
  contains `survey/cruise → station → sample → sequencing event`; every `parentEventID`
  resolves to an existing `eventID`; occurrence `scientificNameID` LSIDs well-formed
  (Novelus row mapped via `--allow-incertae-sedis` to `Biota incertae sedis`
  `urn:lsid:marinespecies.org:taxname:12`, per the OBIS manual's unassigned-sequence path).
- **validate leg:** `*_gbif_validation.json` + `*_obis_validation.json` written;
  OBIS local structural checks 0 issues → GO.

### Online validator probe (read-only, allowed)

Live attempt against `POST https://api.gbif.org/v1/validation` returned **HTTP 403**
(anonymous submissions denied; endpoint confirmed to exist — 400/405 family on related
`/v1/validation` GETs). Recorded in `*_gbif_validation.json` as
`online_status: "auth_required"`, `validation_mode: "local_fallback"`, then the documented
local structural checks ran → verdict GO. This is exactly the pinned documented-fallback
behavior; the report never fabricates an online result.

## 3. Synthetic-fixture status

The fixture (`test/make_fixture.py`) is **fully synthetic** — 5 marine rows (Gadus morhua,
Engraulis encrasicolus, Micromesistius poutassou, Sardina pilchardus, `Novelus asvus` for the
novel-taxon path), §11.1-style manifest, §11.2-enriched parquet with Bio-ORACLE `env_bio_*`
columns, §11.4 flagged TSV. This is **acceptable per PLAN §11.8 rule 4** (structural
verification). NOT yet exercised on real data: (i) the online GBIF validator submission
(auth-required for anonymous), (ii) a real IPT/OBIS upload (deliberately out of scope in v1),
(iii) real WoRMS/GBIF backfill round-trips — those belong to a Phase-1-fed integration run.

## 4. Debug-recovery log (issues found and fixed during the run)

| Signature | Fix applied |
|---|---|
| `TypeError: boolean value of NA is ambiguous` (pandas NA in `in (None, "")`) | `science_name_id` / `is_missing` rewritten to catch pd.NA explicitly |
| meta.xml parsed with namespaced tags while validator searched unqualified | writer now emits elements IN the `dwc/text` namespace with default-namespace serialization; validators use namespaced finds |
| `from xml.etree.ElementTree import ...` lost during a rewrite | restored compile-checked |
| EML title find assumed eml-namespace-qualified children | validator/test scan localnames (EML children are schema-unqualified in real IPT files) |
| `KnownRowTypes` missing after rewrite | `dwca_core.KNOWN_ROWTYPES` restored; smoke-tested |

Each was caught by the battle-test/smoke loop (debug sub-skill verdicts: all RECOVERABLE; no
BLOCKED states remain).

## 5. Checks vs the pinned battle-test requirements

- [x] small synthetic `enriched.parquet` + `flagged_occurrences.tsv` under `test/` (§11.2/§11.4 shapes)
- [x] full pipeline dry-run (DwC-A zips + validation JSONs, **no pushing**)
- [x] pending-record block fires (S2)
- [x] realm gate fires (S3, freshwater refusal with clear OBIS message)
- [x] WoRMS-missing record hard-rejects in the OBIS leg (S4)
- [x] GBIF zip validates structurally (correct meta.xml incl. rowType/term URLs + EML present)
- [x] synthetic-fixture status noted (§3)
- [x] read-only network only; publish commands emitted (`work/publish_commands.sh`), never executed

## 6. Overall verdict

**PASS.** All pinned hard gates demonstrably enforced end-to-end; structural contract holds;
no blockers, no PLAN inconsistencies (no BLOCKERS.md needed). WARN-class observations (do not
block): (1) the synthetic fixture is not real ASV data (§3); (2) online GBIF validation requires
credentials — local structural fallback is fully wired and documented, and the emitted
`online_status` makes the validation provenance explicit. Ready for orchestrator review →
commit/push/deploy are deliberate user/orchestrator actions per pinned rules.