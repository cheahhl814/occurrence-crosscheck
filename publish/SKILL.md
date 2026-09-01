---
name: occurrence-publish
description: 'Phase 3 of the marine-eDNA meta-skill stack: publish validated eDNA occurrences to GBIF and (marine-only) OBIS. Consumes enriched.parquet + flagged_occurrences.tsv (with explicit human sign-off) + run manifest from edna-crosscheck, enforces three hard gates (pending-record sign-off block, OBIS marine-realm gate, WoRMS LSID requirement), builds Darwin Core Archives with a plain-Python writer (stdlib zip + hand-built meta.xml + EML 2.0; no eDNAbridge dependency), produces GBIF occurrence-core archives and OBIS Event-Core archives (survey/cruise → station → sample → sequencing event + occurrence + DNA-derived data + eMoF/OBIS-ENV-DATA), and validates via the GBIF Data Validator API (with documented offline structural fallback) plus local OBIS structural checks. No live IPT/OBIS publishing in v1 — emits ready-to-run publish commands. Sub-skills: preflight (input + signoff gate), gbif-publish, obis-publish, validate. Triggers: "publish eDNA to GBIF/OBIS", "DwC-A publish", "publish occurrence data", "OBIS Event Core", "DNA derived data", "sign off flagged occurrences".'
version: 1.0.1
updated: "2026-09-01"
triggers:
  - "publish eDNA occurrences"
  - "publish to GBIF"
  - "publish to OBIS"
  - "DwC-A publish"
  - "Darwin Core Archive"
  - "OBIS Event Core"
  - "DNA derived data"
  - "sign off flagged occurrences"
  - "occurrence-publish"
---

# Skill: occurrence-publish

> **v1.0.0.** Publish leg of the eDNA meta-skill stack (`PLAN-marine-edna-meta-skill.md` Phase 3).
> Takes the crosscheck output (`enriched.parquet` + `flagged_occurrences.tsv` + run manifest),
> enforces the three pinned HARD GATES, builds GBIF- and OBIS-shaped Darwin Core Archives with a
> **plain-Python DwC-A writer** (stdlib `zipfile` + hand-built `meta.xml` + EML 2.0 XML — no
> eDNAbridge dependency), validates them, and emits ready-to-run publish commands.
> **No live IPT/OBIS publishing calls in v1.**

## 0.5 Ask-User Stop Points (runtime parameters)

> **SP-17 — Image license policy.** Evidence: the `species_images` manifest allows CC-BY-NC images
> for internal reports, while `flag-no-license` rows are always publish-excluded regardless of
> distribution scope. Recommend: "internal: by-nc allowed with attribution" as the default.
> Confirm or pick one of: A) cc-best only (drop all by-nc rows) B) include by-nc with attribution.
> Auto-pick condition: auto-pick B (internal default) whenever the report stays internal; ask
> whenever the report will be shared externally, since by-nc attribution obligations follow the
> image outside the org. This is a preliminary gate — the final ask-user stop point below still
> governs the actual publish action.

## Audience

- **AI agents**: follow the sub-skill chain in order; every ask-user stop point is resolved from
  `preflight.md §4` (pinned decisions) before proceeding.
- **Humans**: run the pipeline via `pixi run` tasks; the sign-off on `flagged_occurrences.tsv`
  is always yours (`signoff_status` ∈ {`approved`, `excluded`}).

## When to Use This Skill

- You have run `edna-crosscheck` (Phase 1) and have all three inputs (§11.7 contract).
- Your dataset is realm-declared: GBIF publishing works for **all realms**; OBIS publishing is
  **marine only** (the sub-skill refuses otherwise — hard gate b).
- Do NOT use for: occurrence cross-checking (→ `edna-crosscheck`), visualization (→
  `occurrence-viz`), or live IPT administration (this skill intentionally does not hold IPT credentials).

## Architecture

```
enriched.parquet (§11.2) + flagged_occurrences.tsv (§11.4) + params.json run manifest (§11.1)
   │
   ▼
1. preflight/preflight-publish        → validate inputs; HARD GATE (a): every flagged row
   │                                     must be approved/excluded, else ABORT with report
   ├─ realm = marine ─────────────┐
   ├─ any realm (GBIF universal)  │
   ▼                              ▼
2. gbif-publish/gbif-publish    3. obis-publish/obis-publish
   occurrence-core DwC-A           HARD GATE (b): realm != marine → REFUSE
   + DNA-derived data ext          Event Core (survey/cruise → station → sample →
   + meta.xml + EML 2.0               sequencing event) + occurrence ext
   → *_gbif_dwca.zip                + DNA-derived data ext + eMoF/OBIS-ENV-DATA
   → publish_commands.sh            HARD GATE (c): WoRMS LSID scientificNameID required
                                    → *_obis_dwca.zip
   │                                     │
   └───────────────┬─────────────────────┘
                   ▼
4. validate/validate-dwca
   GBIF Data Validator (POST /v1/validation; auth/offline → documented local fallback)
   + local OBIS structural checks
   → *_gbif_validation.json + *_obis_validation.json
   Final ask-user stop point: confirm the actual publish (user runs the emitted commands).
```

## HARD GATES (pinned — non-negotiable, implemented in `scripts/`)

| Gate | Rule | Enforcement |
|---|---|---|
| **a. Sign-off** | `flagged_occurrences.tsv` rows with `signoff_status == "pending"` are hard-blocked | `scripts/op_preflight.py` aborts publish with a per-row report until every row is `approved` or `excluded` (PLAN §11.4) |
| **b. OBIS realm** | OBIS does not accept terrestrial/freshwater datasets | `scripts/obis_publish.py` refuses with a clear message when `realm != "marine"` |
| **c. WoRMS LSID** | OBIS requires a WoRMS-valid `scientificNameID` | `scripts/obis_publish.py` hard-rejects any record whose `scientificNameID` is not `urn:lsid:marinespecies.org:taxname:N` |

## Sub-skill routing

| Phase | Sub-skill | Run command |
|---|---|---|
| 1 | `preflight/preflight-publish/SKILL.md` | `pixi run publish-preflight --run-dir RUN --work WORK` |
| 2 | `gbif-publish/gbif-publish/SKILL.md` | `pixi run gbif-publish --run-dir RUN --work WORK` |
| 3 | `obis-publish/obis-publish/SKILL.md` | `pixi run obis-publish --run-dir RUN --work WORK` |
| 4 | `validate/validate-dwca/SKILL.md` | `pixi run validate --run-dir RUN --work WORK [--offline]` |

(`RUN` = directory holding the crosscheck outputs; `WORK` = this skill's run directory, default `.`.
Sub-skill SKILL.md files contain the full procedural detail — this master is a router.)

## Quick start

```bash
# 0. One-time env
pixi install

# 1. Gate check on inputs (run manifest params.json + enriched.parquet + flagged_occurrences.tsv)
pixi run publish-preflight --run-dir /path/to/crosscheck-output --work .

#    → if it aborts: fix flagged rows (set signoff_status=approved/excluded) and re-run.

# 2. Build archives (dry-run by construction: no network, no live push)
pixi run gbif-publish --run-dir /path/to/crosscheck-output --work .
pixi run obis-publish --run-dir /path/to/crosscheck-output --work .   # marine only

# 3. Validate
pixi run validate --run-dir /path/to/crosscheck-output --work .
#    offline: append --offline (local structural checks only)

# 4. Execute the emitted publish commands yourself (final human confirm):
#    work/publish_commands.sh
```

## Outputs (PLAN §11.7 contract)

| Artifact | Emitted by |
|---|---|
| `*_gbif_dwca.zip` — occurrence core + DNA-derived data ext + meta.xml + eml.xml | gbif-publish |
| `*_obis_dwca.zip` — Event Core hierarchy + occurrence ext + DNA-derived data ext + eMoF | obis-publish (marine only) |
| `*_gbif_validation.json`, `*_obis_validation.json` | validate |
| `work/publish_commands.sh` — ready-to-run eDNAbridge/IPT/OBIS-IPT commands | preflight + publish legs |
| `work/gate_report.json` — per-gate verdicts + per-row sign-off report | preflight |

## Network policy

Read-only network access only (GBIF validator POST, docs). **No live IPT/OBIS publishing calls in
v1** — the publish step is a human-executed command. The GBIF leg documents the eDNAbridge
(`skills/edna-gbif-publish`) path as an alternative upload method; the archive built here is
compatible with it (see `docs-corpus/ednabridge-conv/`).

## Conventions inherited from the stack

- Realm is declared dataset-level in the run manifest (`params.json` of the crosscheck run,
  PLAN §11.1); there are no realm if-statements outside the documented gates (b mirrors
  edna-crosscheck's realm-router philosophy at the publish boundary).
- Flags, never silent drops: the sign-off gate surfaces every flagged row; nothing is filtered silently.
- Evidence chain: files, not memory. Each sub-skill consumes the previous phase's artifacts from `work/`.

## Debugging — signature library

When a `pixi run` task fails, match against the signatures below before investigating further.

| Signature in stderr / log | Likely cause | Suggested fix |
|---|---|---|
| `GATE-A: N pending flagged record(s)` | Sign-off incomplete in flagged_occurrences.tsv | Set `signoff_status=approved` or `excluded` for every row; re-run preflight. See gate report for row list. |
| `GATE-B: OBIS refuses ... realm` | Dataset realm is not marine | Publish GBIF only; OBIS datasets must be declared marine at crosscheck preflight. |
| `GATE-C: missing/invalid WoRMS LSID` | `worms_AphiaID` null or `scientificNameID` malformed | Backfill crosswalk (rerun taxon-resolve) or map to `Biota incertae sedis` LSID `urn:lsid:marinespecies.org:taxname:12` if unassigned, per docs-corpus. |
| `ModuleNotFoundError: pandas` | pixi env not installed | `pixi install` and re-run the task. |
| `HTTP 403` from validator | Anonymous submit denied by GBIF | Re-run with `--offline` (local structural checks) or provide credentials via env used by `scripts/validate.py`. |
| `zipfile.BadZipFile` on input | Corrupt/incomplete DwC-A | Re-run the publish sub-skill; do not hand-edit zips. |
| `pixi run` task not found | Wrong working directory | Run all tasks from this skill's root (the dir containing pixi.toml). |
| `verdict: BEHIND-BY-N` from `pixi run update-check` | Upstream ahead of deployed copy | Re-deploy per AGENTS.md §4a; the script prints the canonical fix. |

## Verification

- [ ] `pixi run test-smoke` (structural smoke tests) passes.
- [ ] `pixi run battle-test` runs the synthetic fixture end-to-end; all three hard gates demonstrated.
- [ ] `pixi run update-check` returns `UP-TO-DATE` / `LOCAL-AHEAD` (or `NO-ORIGIN` before first push).

## What NOT to do

- Do not upload anything to any IPT/OBIS instance from within this skill — v1 emits commands only.
- Do not publish with `pending` flagged rows — the gate exists because flags may be either
  misassigned ASVs or genuine range extensions; the human decides.
- Do not reuse the GBIF archive as the OBIS package — OBIS requires the stricter Event Core
  structure (PLAN §6, risk #5).
- Do not edit the PLAN file; write BLOCKERS.md if the contracts (§11.2/§11.4/§11.7) don't match reality.

## Handoff

After `validate/` reports `GO` (or `GO-WITH-WARNINGS`), the user executes
`work/publish_commands.sh` at the final ask-user stop point. This skill's part is done; the
published datasets' DOIs land back in the crosscheck report outside this skill's scope.

## v1.0.1 — runtime ask-user stop point SP-17 (§0.5)

Added a "0.5 Ask-User Stop Points (runtime parameters)" section documenting SP-17 (image license
policy for internal vs. external reports), with an explicit auto-pick condition. It is a
preliminary gate — the final ask-user stop point (`work/publish_commands.sh`, above) remains the
last stop before anything is actually published.