# occurrence-crosscheck

Meta-skill for the eDNA occurrence pipeline: **cross-check → visualize → publish**, realm-aware (marine / freshwater / terrestrial).

Merged from three independently battle-tested skills (v1.0.0 each: `edna-crosscheck` PASS, `occurrence-viz` PASS-WITH-WARNINGS, `occurrence-publish` PASS). Read `SKILL.md` for the routing logic; read `../../../PLAN-marine-edna-meta-skill.md` for the architecture, realm scope, and the pinned §11 data contracts.

```text
skills/occurrence-crosscheck/
├── SKILL.md            # router (start here)
├── merge-manifest.json # provenance + pre-merge SHAs
├── test_smoke.py       # top-level structural checks
├── crosscheck/         # Phase 1 — validation (pixi python env; 84-check suite)
├── viz/                # Phase 2 — publication figures (pixi R env; 22-check suite)
└── publish/            # Phase 3 — DwC-A packaging (pixi python env; 22-check suite)
```

## Quick start

```bash
# Phase 1 — cross-check an ASV table (realm-aware)
cd crosscheck
pixi run crosscheck test/fixtures/synthetic_asv.csv marine test/out
#   → enriched.parquet, crosscheck_report.json, flagged_occurrences.tsv, review_queue.csv

# Phase 2 — figures from any DwC-shaped table (standalone)
cd ../viz
pixi run -e default -- Rscript bin/viz_run.R \
  --input <enriched.parquet or plain occurrence parquet> \
  --config config/run-config.marine.json --outdir viz_out

# Phase 3 — package for GBIF + OBIS (dry-run; gates enforced)
cd ../publish
pixi run battle-test          # or scripts/op_preflight.py / gbif_publish.py / obis_publish.py
```

## Environments

Nested pixi workspaces per sub-skill (R for viz, Python for the others) — see `SKILL.md §Environments` for the rationale. Install each once:

```bash
cd crosscheck && pixi install && cd ../viz && pixi install && cd ../publish && pixi install
```

## Hard gates (never bypass)

1. `publish` records with `signoff_status = pending` are blocked until explicitly approved/excluded.
2. OBIS leg is marine-only; refuses other realms.
3. OBIS leg hard-rejects records without a WoRMS-valid `scientificNameID` LSID.

## Provenance

Pre-merge history per component is preserved as verified git bundles in `../../../archieved/` — see `merge-manifest.json` and `archieved/MIGRATION-occurrence-crosscheck.md`.