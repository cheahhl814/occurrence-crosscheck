# edna-crosscheck

Phase 1 of the eDNA meta-skill stack (`../../../PLAN-marine-edna-meta-skill.md`). Cross-checks eDNA ASV
occurrence tables against occurrence databases (GBIF universally, OBIS additionally for marine) and
environmental data (Bio-ORACLE marine, WorldClim/CHELSA freshwater/terrestrial), realm-aware.

See `SKILL.md` for the full sub-skill router and quick-start commands.

## Install

```bash
pixi install
pixi run setup-fishbase   # one-time R CRAN install of rfishbase (needs libuv, already in pixi.toml)
```

## Run

```bash
pixi run crosscheck <input.csv> <realm> <marker> <out_dir> --user-email <email>
```

`input.csv` needs at minimum: `scientificName`, `decimalLatitude`, `decimalLongitude`, `eventDate`.
`realm` is one of `marine` / `freshwater` / `terrestrial`.
`--user-email` (SP-4, mandatory) is your contact email — sent in the GBIF/OBIS API
`User-Agent` header per their contact-attribution policy, and embedded in any
downstream DwC-A `meta.xml`. The skill preflight HARD-FAILs if missing or malformed;
the agent must ask the user for this value (do not invent, do not default).

## Tests

```bash
pixi run smoke-test                 # structural checks, no network
bash test/run_battle_test.sh        # full realm-matrix battle test, real network calls
```

## Structure

```
edna-crosscheck/
├── SKILL.md                 top-level router
├── README.md                this file
├── pixi.toml / pixi.lock    python 3.11 + R 4.5 env (pandas/pyarrow/duckdb/requests/xarray/rasterio + rfishbase)
├── params.json              example run manifest (PLAN §11.1 schema)
├── preflight.md              evidence chain: input validation, tool audit, FishBase client decision
├── skill-built.md            file inventory
├── battle-test-report.md     structural + realm-matrix battle-test results
├── bin/
│   ├── run-crosscheck.sh     bash-first orchestrator (chains all 6 sub-skills)
│   └── skill-update-check.py self-update check (git SHA diff, no GitHub API)
├── lib/netlog.py             shared HTTP client with per-run call_log.jsonl (source-tagged)
├── preflight/                input validation + params.json
├── realm-router/             the only realm if-statement in the whole skill
├── taxon-resolve/            WoRMS + GBIF + FishBase crosswalk cache (sqlite)
├── fishbase-traits/          rfishbase R subprocess -> trait pull
├── env-extract/               Bio-ORACLE / WorldClim bulk-download + local extraction
├── crosscheck/                final assembly + QC flags -> enriched.parquet / crosscheck_report.json / flagged_occurrences.tsv
├── docs-corpus/               offline docs for gbif/obis/worms/fishbase/bio-oracle/worldclim-chelsa
└── test/                      synthetic fixture + smoke test + battle-test runner
```

## Data contracts

Outputs conform exactly to PLAN §11 (`enriched.parquet`, `crosscheck_report.json`,
`flagged_occurrences.tsv`, `review_queue.csv`) — these are shared with two sibling skills
(`occurrence-viz`, `occurrence-publish`) being built in parallel against the same schemas.
