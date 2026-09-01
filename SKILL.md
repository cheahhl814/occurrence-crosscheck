---
name: occurrence-crosscheck
description: "Meta-skill for the eDNA occurrence pipeline: (1) cross-check eDNA ASV observations against GBIF/OBIS/WoRMS/FishBase + Bio-ORACLE/WorldClim environmental envelopes (realm-aware: marine/freshwater/terrestrial); (2) publication-ready occurrence figures (maps, profiles, envelopes, trait space); (3) publish validated observations as DwC-A to GBIF/IPT and OBIS (Event Core + DNA-derived data). Router — routes to the three phase sub-skills: crosscheck/, viz/, publish/. Use when asked to 'cross-check eDNA results', 'plot species occurrence', or 'publish eDNA to GBIF/OBIS'."
version: 2.0.0
updated: "2026-08-31"
triggers:
  - "cross-check eDNA results"
  - "validate ASV table against GBIF"
  - "QC eDNA occurrences"
  - "ground-truth eDNA detections"
  - "plot species occurrence"
  - "publication maps for occurrence data"
  - "publish eDNA to GBIF"
  - "publish to OBIS"
  - "occurrence-crosscheck"
requires:
  - "pixi (nested per-sub-skill workspaces; see README)"
  - "network access (read-only GETs; publish legs dry-run by default)"
---

# Meta-skill: occurrence-crosscheck

v2.0.0 — merged from three independently-built skills (see `archieved/MIGRATION-occurrence-crosscheck.md` in the workspace root; full pre-merge git histories preserved as verified git bundles).

Design source of truth: `../../../PLAN-marine-edna-meta-skill.md` — in particular the **realm scope banner** (marine vs freshwater vs terrestrial routing) and **§11 pinned cross-skill data contracts**, which are the filesystem boundary between the sub-skills.

## Architecture — this is a router, not a doer

```
nf-edna ASV table
   │
   ▼  realm declared at preflight: marine | freshwater | terrestrial
── crosscheck/ ──► enriched.parquet, crosscheck_report.json,
│                  flagged_occurrences.tsv (signoff gate), review_queue.csv
│
├─► viz/      ◄─ any DwC-shaped table (standalone §11.6 contract)
│
└─► publish/  ◄─ enriched.parquet + signed-off flagged_occurrences.tsv
                GBIF DwC-A zip + OBIS Event-Core zip (marine-only)
```

## Phase routing

| Phase | Sub-skill dir | Sub-skill SKILL.md entry | Invoke when |
|---|---|---|---|
| 1. Validate | `crosscheck/` | `crosscheck/SKILL.md` | New ASV table to ground-truth against GBIF/OBIS/WoRMS/FishBase + env envelopes |
| 2. Visualize | `viz/` | `viz/SKILL.md` | Publication maps/profiles/envelopes/trait-space from any occurrence table |
| 3. Publish | `publish/` | `publish/SKILL.md` | Convert validated observations into GBIF/OBIS DwC-A packages |

**Stop-point policy is inherited from each sub-skill.** Cross-skill gates that MUST NOT be bypassed:

1. `publish/` refuses records whose `signoff_status` is `pending` (PLAN §11.4) — user sign-off is explicit.
2. `publish/obis-publish` refuses non-`marine` realms.
3. `publish/obis-publish` hard-rejects records without a WoRMS-valid `scientificNameID` LSID.

## Environments (nested pixi workspaces — deliberate)

Each sub-skill keeps its own pinned `pixi.toml`/`pixi.lock`/`.pixi` because their toolchains diverge (viz is R-only; crosscheck/publish are Python-first). Do **not** merge the envs.

```bash
cd crosscheck && pixi run crosscheck test/fixtures/synthetic_asv.csv marine test/out   # Phase 1
cd viz       && pixi run -e default -- Rscript bin/viz_run.R --input F.parquet --config config/run-config.marine.json --outdir viz_out   # Phase 2
cd publish   && pixi run battle-test                                                    # Phase 3 dry-run
```

## Schemas (frozen contracts — change via PLAN §11 only)

- §11.1 run manifest `params.json` · §11.2 `enriched.parquet` · §11.3 `crosscheck_report.json`
- §11.4 `flagged_occurrences.tsv` (`signoff_status`: `pending` blocks everything downstream)
- §11.5 `review_queue.csv` · §11.6 viz input contract · §11.7 publish input contract

## Migration history

| Pre-merge skill | HEAD at merge | Now at |
|---|---|---|
| edna-crosscheck | `01e6582` | `crosscheck/` |
| occurrence-viz | `177d9d3` | `viz/` |
| occurrence-publish | `8878791` | `publish/` |

Full histories: `../../../archieved/*.bundle` (verified complete; `git clone <bundle> <name>` to restore).

## Verification

- [ ] `python3 test_smoke.py` — top-level structural checks (router wiring, sub-skill frontmatter, contracts presence)
- [ ] Per-sub-suite: `cd crosscheck && python3 test/test_smoke.py` (84 checks) · `cd viz && python3 test_smoke.py` (22) · `cd publish && python3 test_smoke.py` (22)
- [ ] Realm matrix: `cd crosscheck && bash test/run_battle_test.sh`
- [ ] Historical battle-test reports: `*/battle-test-report.md` (v1.0.0 verdicts: PASS / PASS-WITH-WARNINGS / PASS)

- `species-images` (crosscheck v2.3.0): citable per-species photos (iNat-first, GBIF fallback) as a flagged manifest — visualized by the viz sub-skill via `--images` (fig 07 contact sheet + map thumbnails). See PLAN §11.9.
