# occurrence-publish

**v1.0.1** · Phase 3 of the eDNA meta-skill stack (`PLAN-marine-edna-meta-skill.md`). Publishes
crosscheck-validated eDNA occurrences to **GBIF** (all realms) and **OBIS** (marine only) as
Darwin Core Archives, behind three pinned hard gates, with **no live publishing calls in v1**.

## Contents

- [🚀 Installation](#-installation)
- [💡 Usage](#-usage)
- [🔬 Pipeline overview](#-pipeline-overview)
- [🧰 Tools](#-tools)
- [🔄 Update check](#-update-check)
- [📁 Repository layout](#-repository-layout)
- [🔒 Hard guarantees](#-hard-guarantees)
- [Provenance](#provenance)

## 🚀 Installation

```bash
git clone https://github.com/cheahhl814/occurrence-crosscheck.git   # this skill lives in publish/
cd occurrence-crosscheck/publish
pixi install
```

## 💡 Usage

```bash
pixi run publish-preflight --run-dir /path/to/crosscheck-output --work .
pixi run gbif-publish     --run-dir /path/to/crosscheck-output --work .
pixi run obis-publish     --run-dir /path/to/crosscheck-output --work .   # marine only
pixi run validate         --run-dir /path/to/crosscheck-output --work .
# then review + execute work/publish_commands.sh (final human confirm)
```

Input contract (PLAN §11.7):

- `enriched.parquet` — output of `edna-crosscheck` (§11.2 column contract).
- `flagged_occurrences.tsv` — §11.4 gate file, adds `signoff_status` column.
- run manifest — the crosscheck run's `params.json` (realm, marker, bbox, env source).

## 🔬 Pipeline overview

| Sub-skill | Script | Hard gates |
|---|---|---|
| `preflight/` | `scripts/op_preflight.py` | (a) pending sign-off records block publish |
| `gbif-publish/` | `scripts/gbif_publish.py` | reads gate report; aborts on gate failure |
| `obis-publish/` | `scripts/obis_publish.py` | (b) realm != marine refuses; (c) WoRMS LSID hard-reject |
| `validate/` | `scripts/validate.py` | — (reports only) |

What each leg does:

1. **Gate** — refuses to publish until every row of `flagged_occurrences.tsv` has an explicit
   human `signoff_status` of `approved` or `excluded` (`pending` rows hard-block; PLAN §11.4).
2. **gbif-publish** — builds an occurrence-core DwC-A (+ DNA-derived data extension, eMoF as
   applicable) with a plain-Python writer: stdlib `zipfile` + hand-built `meta.xml` + EML 2.0
   XML. No eDNAbridge dependency. Emits a ready-to-run IPT upload command (eDNAbridge path
   documented as the reference workflow).
3. **obis-publish** (marine datasets only — refuses otherwise) — builds the OBIS Event-Core
   package: `survey/cruise → station → sample → sequencing event` hierarchy + occurrence
   extension + DNA-derived data extension + eMoF/OBIS-ENV-DATA rows (Bio-ORACLE `env_bio_*`
   values slot in as eMoF measurements when present). Hard-rejects records without a
   WoRMS-valid `scientificNameID` LSID.
4. **validate** — submits the GBIF archive to the GBIF Data Validator API
   (`POST https://api.gbif.org/v1/validation`); falls back to documented local structural
   checks when the online endpoint is unreachable/auth-denied (`--offline` forces fallback).
   OBIS-side checks are local structural checks only (never a live IPT push).

## 🧰 Tools

- Python ≥3.11 via pixi (conda-forge): `pandas`, `pyarrow`, `requests`. Nothing else.
- Plain-Python DwC-A writer: stdlib `zipfile` + hand-built `meta.xml` + EML 2.0 (no eDNAbridge dependency).
- Offline docs snapshots in `docs-corpus/` — read them instead of hallucinating flags:
  [DwC-A profile](docs-corpus/dwca-profile/README.md) · [EML 2.x](docs-corpus/eml-2/README.md) ·
  [DNA-derived data extension](docs-corpus/dna-derived-data-extension/README.md) ·
  [OBIS DNA data](docs-corpus/obis-dna-data/README.md) ·
  [GBIF data validator](docs-corpus/gbif-data-validator/README.md) ·
  [eDNAbridge/obis ecosystem reference](docs-corpus/ednabridge-conv/README.md).

## 🔄 Update check

`pixi run update-check` diffs this checkout's git SHA against upstream via `git fetch`.
Verdicts: `UP-TO-DATE` (0) · `LOCAL-AHEAD` (0) · `BEHIND-BY-N` (1 — re-sync this directory from
the `occurrence-crosscheck` repo) · `OFFLINE` (2) · `NO-ORIGIN` (2).
Battle-test artifacts land under `work/` (gitignored).

## 📁 Repository layout

```
publish/
├── SKILL.md                    # orchestrator (router) — start here
├── README.md                   # this file
├── pixi.toml / pixi.lock       # conda-forge env
├── params.json                 # example manifest (§11.7)
├── preflight/preflight-publish/  # gate (a): pending sign-off blocks
├── gbif-publish/               # GBIF occurrence-core DwC-A builder
├── obis-publish/               # OBIS Event-Core builder
├── validate/validate-dwca/     # GBIF validator (API + offline fallback)
├── scripts/                    # op_preflight, gbif_publish, obis_publish, validate, dwca_core
├── docs-corpus/                # offline API/schema snapshots
├── test/                       # synthetic fixture + battle-test runner
├── work/                       # run outputs (gitignored)
├── skill-built.md              # build evidence
└── battle-test-report.md       # smoke + battle-test verdicts
```

## 🔒 Hard guarantees

1. **Sign-off gate** — `pending` flagged records can never reach publish; the abort report lists
   every offending row.
2. **OBIS realm gate** — `realm != marine` → OBIS leg exits with a clear refusal message.
3. **WoRMS LSID gate** — OBIS leg hard-rejects records whose `scientificNameID` is not
   `urn:lsid:marinespecies.org:taxname:N`.
4. **No live publishing in v1** — the skill emits ready-to-run commands; a human executes them.

## Provenance

Built with the [skill-forge](https://github.com/cheahhl814/skill-forge) meta-skill. Pattern
adopted from BettaMt-agents / bacterial-genome-analysis (AiX-BIO skill convention:
preflight → build → debug → battle-test evidence chain).

`pixi run battle-test` builds a small synthetic enriched.parquet + flagged_occurrences.tsv
under `test/` (synthetic fixture — acceptable per PLAN §11.8 rule 4), runs the full pipeline in
dry-run mode, and asserts: pending-record block fires, realm gate fires, LSID-missing record
hard-rejects in the OBIS leg, and the GBIF zip validates structurally (correct meta.xml +
EML present). See `battle-test-report.md`.
