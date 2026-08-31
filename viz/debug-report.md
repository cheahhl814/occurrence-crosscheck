# Debug report — occurrence-viz build (construct-time debug phase)

Run:        /home/cheahhl814/claude_workspace/bioinformatics/AIx-BIO/skills/occurrence-viz
Generated:  2026-08-31 (debug phase of the bioinfo-skill-creator 4-phase chain)
Inputs:     skill-built build errors + pixi env stderr (all captured in this session)

## Overall verdict

**RECOVERABLE** ✅ — all 6 defects found during first execution were diagnosed, fixed, and re-verified; R parse checks, smoke tests (22/22), and full execution all pass afterwards.

## Defect ledger (failure signature → diagnosis → fix → verification)

| # | Signature in stderr | Likely cause (signature-library entry that led here) | Fix applied | Verified by |
|---|---|---|---|---|
| D1 | `sample.int: cannot take a sample larger than the population when 'replace = FALSE'` in test/make_test_fixture.R | `sample()` over the 4-element flag pool with `nrow(dm)` draws | added `replace = TRUE` | fixture generation: 822 + 603 + 120 rows written |
| D2 | `bin/plot_map.R: error: "marine" is not a valid option` (optparse usage dump) | viz_run.R passed the 3-word `--input-label` unquoted to the shell | `run_phase()` now `shQuote()`s every arg | quoted cmd echoed; workers parse args |
| D3 | `Error: arrow package required for parquet input` despite pixi env having arrow | driver invoked bare `Rscript` → resolved to system R (no arrow) instead of the env R | driver invokes `file.path(R.home("bin"), "Rscript")` (same interpreter as caller) | workers load 822×15 parquet |
| D4 | `Error in (function (..., row.names = NULL...)`: differing number of rows 1, 0 in build_report.R ledger parser | `as.data.frame(fromJSON(...))` explodes when an `extra` field is a zero-length list | records parsed field-wise into single-row data.frames with fallbacks | 6-record ledger parsed; captions written |
| D5 | `The package "Hmisc" is required` in `stat_summary(fun.data="mean_cl_normal")` | mean±CI helper is an Hmisc-derived function ggplot2 no longer ships | mean/se/CI computed with dplyr, drawn with `geom_pointrange(aes(ymin,ymax))` + separate raw-points layer | 04_env_envelope PNG+PDF render, no warnings |
| D6 | `Error: crs not found: is it missing?` for every geom_sf figure (01/02/06) + `GDAL Error 1: PROJ: ... Open of <env>/share/proj failed` | conda-forge `proj` ≥9 packages do NOT ship conda activate scripts, so `PROJ_DATA` is unset inside `Rscript` (pixi run or not) → sf cannot open `proj.db` | `.proj_data_init()` in bin/lib_viz.R: derives the env prefix from `system.file(package="sf")`, sets `PROJ_DATA`/`PROJ_LIB` when `proj.db` exists there; safe no-op when already set | 01/02/06 PNG+PDF render; PROJ fix portable to any pixi env |
| D7 (minor) | `scale_fill_viridis_d is not an exported object from 'namespace:viridis'` | the `_d` variants are native ggplot2 exports, not viridis-pkg exports | `make_fill_scale()` now uses `ggplot2::scale_fill_viridis_d` (begin/end trimmed for legibility) | legend renders, palette warning gone |
| D8 (minor) | zero-width space in `warn_msg <- function(...)...` (invisible U+200B from an edit accident) → `unexpected input` parse error | editor artifact | stripped all U+200B/U+FEFF from lib_viz.R | `parse()` OK |

## Post-fix verification

- `Rscript -e "invisible(parse(f))"` OK for all 6 R scripts.
- `python3 test_smoke.py` → **22/22 passed**.
- Full execution: marine fixture (822 rows, 6 figures), terrestrial fixture (603 rows, 5 figures + 1 documented skip), minimal-DwC fixture (maps-only + 3 logged §11.6 skips), real OBIS fixture (500 records, live API, 5 figures).
- `bin/skill-update-check.py` compiles + runs (NO-GIT verdict expected pre-commit; exit 2 informational).
- `pixi lock --dry-run`: lock file would not change (parses clean).

## Handoff

Verdict RECOVERABLE → no rebuild needed; Phase 4 (battle-test) proceeds. `battle-test-report.md` written separately with PASS-WITH-WARNINGS-eligible evidence.