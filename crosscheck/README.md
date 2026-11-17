# edna-crosscheck

**v1.1.0.** Phase 1 of the eDNA meta-skill stack (`../../../PLAN-marine-edna-meta-skill.md`). Cross-checks eDNA ASV
occurrence tables against occurrence databases (GBIF universally, OBIS additionally for marine) and
environmental data (Bio-ORACLE marine, WorldClim/CHELSA freshwater/terrestrial), realm-aware.

See `SKILL.md` for the full sub-skill router and quick-start commands.

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
git clone https://github.com/cheahhl814/occurrence-crosscheck.git   # this skill lives in crosscheck/
cd occurrence-crosscheck/crosscheck
pixi install
pixi run setup-fishbase   # one-time R CRAN install of rfishbase (needs libuv, already in pixi.toml)
```

## 💡 Usage

```bash
pixi run crosscheck <input.csv> <realm> <marker> <out_dir> --user-email <email>
```

`input.csv` needs at minimum: `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate`.
`realm` is one of `marine` / `freshwater` / `terrestrial`.
`--user-email` (SP-4, mandatory) is your contact email — sent in the GBIF/OBIS API
`User-Agent` header per their contact-attribution policy, and embedded in any
downstream DwC-A `meta.xml`. The skill preflight HARD-FAILs if missing or malformed;
the agent must ask the user for this value (do not invent, do not default).

Other entry points (see `SKILL.md` §Quick start for the full table):
`pixi run species-list` (inverted/envelope mode), `pixi run coordinates-checklist`
(coordinate mode), `pixi run genus-narrow`, `pixi run habitat-iucn`, `pixi run species-images`.

## 🔬 Pipeline overview

Hard-ordered chain (PLAN §4/§7 risk #3):

```
preflight -> realm-router -> taxon-resolve -> fishbase-traits -> env-extract -> crosscheck
```

- **preflight** — input validation + `params.json` run manifest; `--user-email` gate (SP-4).
- **realm-router** — the ONLY place `realm` branching lives; downstream sub-skills read `routing.json`.
- **taxon-resolve** — WoRMS/GBIF/FishBase crosswalk cache (SQLite); ambiguous matches go to `review_queue.csv`.
- **fishbase-traits** — depth/trophic/body-size via rfishbase (must precede env-extract: depth picks the marine layer).
- **env-extract** — Bio-ORACLE (marine) / WorldClim-CHELSA (freshwater/terrestrial), bulk-download-once + local extraction.
- **crosscheck** — joins everything; emits `enriched.parquet`, `crosscheck_report.json`, `flagged_occurrences.tsv`, `review_queue.csv`. Flags, never silent drops.

## 🧰 Tools

- Python 3.11 + R 4.5 via pixi (conda-forge/bioconda): pandas/pyarrow/duckdb/requests/xarray/rasterio + rfishbase.
- Live read-only APIs: GBIF, OBIS, WoRMS, FishBase (via rfishbase S3 snapshots), Bio-ORACLE ERDDAP, WorldClim.
- Offline docs snapshots in `docs-corpus/` for gbif/obis/worms/fishbase/bio-oracle/worldclim-chelsa — consult these before inventing flags or endpoints.

## 🔄 Update check

```bash
pixi run update-check
# UP-TO-DATE (0) / LOCAL-AHEAD (0) / BEHIND-BY-N (1) / OFFLINE (2) / NO-ORIGIN (2)
```

When `BEHIND-BY-N`, re-sync this directory from the upstream `occurrence-crosscheck` repository.
Test suites: `pixi run smoke-test` (structural, no network) · `bash test/run_battle_test.sh` (full realm matrix, real network).

## 📁 Repository layout

```
crosscheck/
├── SKILL.md                 top-level router
├── README.md                this file
├── pixi.toml / pixi.lock    python 3.11 + R 4.5 env
├── params.json              example run manifest (PLAN §11.1 schema)
├── preflight.md             evidence chain: input validation, tool audit, FishBase client decision
├── skill-built.md           file inventory
├── battle-test-report.md    structural + realm-matrix battle-test results
├── bin/
│   ├── run-crosscheck.sh    bash-first orchestrator (chains all 6 sub-skills)
│   └── skill-update-check.py self-update check (git SHA diff, no GitHub API)
├── lib/                     netlog.py (HTTP client + call_log.jsonl), geo.py (geodesic ring helpers)
├── preflight/               input validation + params.json
├── realm-router/            the only realm if-statement in the whole skill
├── taxon-resolve/           WoRMS + GBIF + FishBase crosswalk cache (sqlite)
├── fishbase-traits/         rfishbase R subprocess -> trait pull
├── env-extract/             Bio-ORACLE / WorldClim bulk-download + local extraction
├── crosscheck/              final assembly + QC flags -> enriched.parquet / crosscheck_report.json / flagged_occurrences.tsv
├── docs-corpus/             offline docs snapshots
└── test/                    synthetic fixture + smoke test + battle-test runner
```

## 🔒 Hard guarantees

- **Flags, never silent drops** — every suspicious record is flagged (`OUT_OF_RANGE`, `ENVELOPE_VIOLATION`, `GENUS_ONLY`, `NO_RECORD`, …) and routed to `flagged_occurrences.tsv` / `review_queue.csv`; nothing is discarded silently.
- **SP-4 contact attribution** — preflight HARD-FAILs without a valid `--user-email`; sent as the GBIF/OBIS `User-Agent` and embedded in downstream DwC-A `eml.xml`.
- **Realm isolation** — realm branching exists only in `realm-router`; every other sub-skill reads `routing.json`.
- **Read-only network** — GET-only calls; no publishing from this skill (that is `publish/`).

## Provenance

Built with the [skill-forge](https://github.com/cheahhl814/skill-forge) meta-skill (AiX-BIO convention:
preflight → build → debug → battle-test). Outputs conform exactly to PLAN §11 (`enriched.parquet`,
`crosscheck_report.json`, `flagged_occurrences.tsv`, `review_queue.csv`) — shared with the sibling
`viz/` and `publish/` sub-skills in this repository.
