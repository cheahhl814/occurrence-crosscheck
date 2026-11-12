---
name: edna-crosscheck-crosscheck
description: Final assembly + realm-aware QC flagging. Joins occurrence data against the taxon crosswalk, FishBase traits, env values, and occurrence corroboration counts (GBIF+OBIS marine / GBIF-only non-marine); emits enriched.parquet, crosscheck_report.json, and flagged_occurrences.tsv per PLAN §11. Flags, never silent drops.
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "edna-crosscheck crosscheck flags"
  - "emit crosscheck report"
disable-model-invocation: true
---

# crosscheck/edna-crosscheck-crosscheck

## Inputs
- Original occurrence CSV, `work_dir` (crosswalk sqlite, fishbase_pull.json, env_values.csv,
  occurrence_counts.json — all produced by the earlier sub-skills), `routing.json`, `params.json`.

## Outputs (PLAN §11 pinned schemas — byte-for-byte, shared with sibling skills)
- `enriched.parquet` (§11.2)
- `crosscheck_report.json` (§11.3)
- `flagged_occurrences.tsv` (§11.4, `signoff_status` defaults to `"pending"`)
- `review_queue.csv` is produced upstream by taxon-resolve and copied into the run's `out_dir` by the
  orchestrator (`bin/run-crosscheck.sh`), not regenerated here.

## Procedure
```bash
python3 occurrence_lookup.py <names_file> <routing.json> <params.json> <work_dir>   # GBIF(+OBIS marine) corroboration
python3 crosscheck.py <occurrences.csv> <work_dir> <routing.json> <params.json> <out_dir>
```

## Ask-user stop points

**SP1 — ENVELOPE_VIOLATION implementation without a per-record measured depth column.** Evidence: the
pinned input contract (PLAN §11.6/nf-edna ASV table) doesn't guarantee a per-occurrence measured sample
depth; only the taxon-level FishBase depth *range* is available. Recommend: implement the envelope check
as "env layer returned no value (fill) for a taxon with a valid FishBase depth range" — a real, flaggable
signal — rather than fabricating a depth comparison the input data can't support. Decision (documented
limitation, not silently glossed over): implemented as described in `crosscheck.py::envelope_violation`;
a future version with a real per-sample depth/elevation field should tighten this to a numeric range
comparison.

**SP2 — ON_LAND proxy without a bundled coastline polygon.** Evidence: a real on/off-water check needs a
coastline/EEZ polygon (e.g. Natural Earth), which is a real dependency this skill doesn't currently ship.
Recommend: use bbox-membership as a cheap proxy (flag points falling outside the declared realm bbox) and
mark it explicitly as a known ceiling. Decision (ponytail-flagged limitation): implemented as bbox-membership;
`# ponytail: bbox-membership proxy, swap for a real coastline mask if false positive/negative rate on
production data proves it inadequate`.

**SP3 — qc_level thresholds (`ok`/`warning`/`error`).** Evidence: PLAN §11.2 defines the enum but not
the exact mapping from flag combinations to level. Recommend: `error` only for `unresolved` taxonomy
(genuinely can't validate anything downstream), everything else that has any flag is `warning`, no flags
is `ok`. Decision (pinned as an open parameter, resolved here): implemented exactly this way in
`crosscheck.py`.

## Signature library

| stderr / evidence pattern | likely cause | fix |
|---|---|---|
| `crosscheck_report.json` summary counts don't sum to `total_records` | a taxon had `taxon_match_status == "genus_only"` (counted in neither resolved/ambiguous/unresolved by design — it's its own bucket, flagged via `GENUS_ONLY` instead) | expected; genus_only is intentionally excluded from the resolved/ambiguous/unresolved tally — cross-check against `flags.GENUS_ONLY` instead |
| `flagged_occurrences.tsv` is empty for a run you expected flags on | every record was clean, or the realm's `qc_checks` list doesn't include the check you expected (e.g. `ON_LAND` for terrestrial — by design, see realm-router) | check `routing.json.qc_checks` for the realm before assuming a bug |
| `enriched.parquet` missing expected `env_bio_*`/`env_wc_*` columns | `env_values.csv` had zero rows (env-extract failed silently upstream) or the wrong prefix was used | check `env-extract`'s stderr and `work_dir/call_log.jsonl` for `bio-oracle`/`worldclim-chelsa` entries before re-running crosscheck |
