# Preflight — `occurrence-publish` (Phase 3 of the eDNA Meta-Skill Stack)

**Date:** 2026-08-31
**Phase:** 1 of 4 (bioinfo-skill-creator evidence chain)
**Verdict:** **GO** (no blocking findings; 2 recorded deviations, below)

---

## 1. Evidence collected

| Check | Evidence | Result |
|---|---|---|
| RUN_DIR exists | `/home/cheahhl814/claude_workspace/bioinformatics/AIx-BIO/skills/occurrence-publish` created | ✅ |
| `git init --initial-branch=master` | Initialized empty repo; zero commits yet (first commit after build) | ✅ |
| Not pushed to GitHub | No remote configured; per task instructions DO NOT push | ✅ |
| Not deployed to `~/.pi/agent/skills/` | Nothing copied there; per task instructions | ✅ |
| PLAN read | `PLAN-marine-edna-meta-skill.md` read in full (§2 arch, §3 conventions, §6 spec, 🔴 SCOPE banner, §11.2/§11.4/§11.7 contracts) | ✅ |
| Meta-skill read | `~/.pi/agent/skills/bioinfo-skill-creator/SKILL.md` + `build/skill-builder/SKILL.md` + `test_smoke.py` | ✅ |
| pixi on PATH | `pixi 0.70.1` | ✅ |
| System python | Python 3.12.3 (pixi env will pin ≥3.11 per pinned decision) | ✅ |
| Disk free | 135 GB at RUN_DIR (≥ 5 GB required) | ✅ |
| PLAN internal consistency | §6 vs §11 contracts vs pinned decisions cross-checked — **no contradiction found**; `BLOCKERS.md` not needed | ✅ |
| Sibling skills | `edna-crosscheck` and `occurrence-viz` not yet on disk (parallel builds in flight). Coupling is ONLY files per §11 — no imports of their code. | ✅ |

## 2. Upstream tool / dependency inventory

Primary language: **Python 3.11+ via pixi** (pinned). Bash-first orchestration via `pixi run` tasks.

| Tool / library | Source | Role | pixi channel |
|---|---|---|---|
| python | conda-forge | DwC-A writer (stdlib only: `zipfile`, `xml.etree`, `csv`), gate logic, validators | conda-forge |
| pandas | pypi/conda-forge | read `enriched.parquet` / `flagged_occurrences.tsv` / manifest | conda-forge |
| pyarrow | conda-forge | parquet I/O for `enriched.parquet` (§11.2 contract) | conda-forge |
| requests | conda-forge | read-only network: GBIF Data Validator POST, docs fetch | conda-forge |

**Explicitly NOT a dependency (pinned):** `eDNAbridge` (R) — the GBIF leg *documents/wraps* the
eDNAbridge path conceptually and the docs-corpus captures its conventions, but the runnable code
path here is our own plain-Python DwC-A builder. No live IPT/OBIS publishing calls in v1 —
publish commands are emitted as ready-to-run shell commands the user executes.

## 3. Architecture resolved (from PLAN §6 + pinned decisions)

```
enriched.parquet + flagged_occurrences.tsv (signed off) + run manifest (params.json of the crosscheck run)
   │
   ▼
sub-skill 1: preflight/      → validate §11.2/§11.4 inputs, sign-off gate (HARD GATE a), realm routing
sub-skill 2: gbif-publish/   → plain-Python DwC-A (occurrence core + DNA-derived data ext + meta.xml + EML 2.0)
                               → emits ready-to-run IPT/eDNAbridge commands; produce *_gbif_dwca.zip
sub-skill 3: obis-publish/   → marine-only (HARD GATE b: realm != marine → refuse)
                               Event Core (survey/cruise → station → sample → sequencing event)
                               + Occurrence ext + DNA-derived data ext + eMoF/OBIS-ENV-DATA
                               (HARD GATE c: WoRMS LSID scientificNameID required, else hard-reject)
sub-skill 4: validate/       → GBIF Data Validator (online POST /v1 validator; documented offline fallback:
                               local structural checks) + OBIS local structural checks (never a live IPT push)
```

## 4. Ask-user stop points — resolved from PINNED DECISIONS (autonomous mode)

| SP | Question | Resolution (source) |
|---|---|---|
| SP1 | pixi install? | pixi 0.70.1 already on PATH → proceed (auto-pick, unambiguous) |
| SP2 | DwC-A writer implementation | Plain Python stdlib (`zipfile` + hand-built `meta.xml` + EML 2.0 as XML); do NOT depend on eDNAbridge (pinned) |
| SP3 | Nextflow runner? | **No** — bash-first; PLAN §3 states no Nextflow runner for this stack (pinned) |
| SP4 | git init? | Done (`--initial-branch=master`), commit locally only, no push (pinned) |
| SP5 | Sub-skill granularity | Exactly 4: `preflight/`, `gbif-publish/`, `obis-publish/`, `validate/` (pinned, PLAN §6) — supersedes the meta-skill default 5-sub-skill template |
| SP6 | Lite tree (`target_tiers`)? | `["large"]` only — pinned decisions specify none; parallel-build context, keep the tree lean |
| SP7 | Battle-test fixture | Synthetic fixture under `test/` explicitly mandated by pinned decisions (PLAN §11.8 rule 4 allows) |
| SP8 | Live publishing calls? | None in v1 — read-only network only (GBIF validator, docs); publish commands emitted for the user (pinned) |

## 5. HARD GATES to implement exactly (pinned — carried into params.json)

- **(a) Sign-off gate (§11.4):** every `flagged_occurrences.tsv` row with `signoff_status == "pending"`
  is hard-blocked; publish aborts with a report until every row is `approved` or `excluded`.
- **(b) OBIS realm gate:** `obis-publish` refuses with a clear message when `realm != "marine"`
  (OBIS does not accept terrestrial/freshwater datasets).
- **(c) WoRMS LSID gate:** `obis-publish` hard-rejects any record whose `scientificNameID` is not a
  WoRMS-valid LSID (`urn:lsid:marinespecies.org:taxname:N`).

## 6. Input contracts (PINNED, §11.2 / §11.4 / §11.7)

- **Inputs:** `enriched.parquet` (columns per §11.2) + `flagged_occurrences.tsv` (§11.4, adds
  `signoff_status`) + run manifest (`params.json` of the edna-crosscheck run, §11.1 — `realm` is dataset-level).
- **Outputs (§11.7):** `*_gbif_dwca.zip` + `*_obis_dwca.zip` + `*_gbif_validation.json` +
  `*_obis_validation.json` (+ `publish_commands.sh` ready-to-run publishing commands + gate report JSONs).

## 6. Deviations (from the meta-skill defaults / PLAN)

1. **Sub-skill granularity:** the meta-skill default is 5 sub-skills (preflight/run/qc/debug/battle-test);
   per the pinned decisions we ship exactly 4 run sub-skills (`preflight/`, `gbif-publish/`,
   `obis-publish/`, `validate/` per PLAN §6). Debug + battle-test conventions live in the master
   `SKILL.md` + `test_smoke.py` rather than as sub-skill directories (they are build-time phases
   consumed from `bioinfo-skill-creator`, consistent with how `bioinfo-skill-creator` itself ships them).
2. **Ask-user stop points:** all 8 potential SPs were resolved autonomously from the pinned decisions
   in the task prompt (§4 above) instead of blocking on user input — per the task's autonomous-build
   instruction. Each resolution cites its pinned source.

## 7. Verdict

**GO.** All pinned decisions are implementable as designed; input contracts are unambiguous;
pixi and disk are available; no PLAN inconsistency requiring BLOCKERS.md.