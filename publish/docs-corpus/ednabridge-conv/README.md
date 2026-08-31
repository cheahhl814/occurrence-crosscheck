# docs-corpus/ednabridge-conv — eDNAbridge + obistools conventions (REFERENCE ONLY)

Source captured 2026-08-31: https://github.com/gbif/eDNAbridge (README + R module layout +
test fixtures). Per the pinned decisions this is reference material: the runnable code path of
`occurrence-publish` is the plain-Python DwC-A builder in `scripts/dwca_core.py` — eDNAbridge
is NOT a runtime dependency of this skill.

## What eDNAbridge is

R package (Epi Group / NZ Ministry for the Environment, hosted under gbif/) that transforms
eDNA occurrence data into DwC-A and publishes via a GBIF IPT. Modules (from `R/`):

1. **Ingest** (`01_ingest_*`) — Wilderlab API or custom CSV with column mappings.
2. **Validate** (`02_validate_*`) — required columns, coordinates, scientificName vs GBIF
   backbone, no additional terms beyond the DwC schema (`val_validate_no_additional_terms`),
   issue rows with error levels (mirror of obis-data-qc style).
3. **Generate DwC-A** (`03_generate_dwc_*`) — `gen_tibble_to_dwc_frames()` (occurrence core +
   optional eMoF + optional DNA extension), `eml_base()/eml_set_*`, `meta_xml_base()/
   meta_xml_add_file()`, `gen_make_dwc_archive()`.
4. **Upload to IPT** (`04_upload_*`) — `ipt_login`, `ipt_register_resource`,
   `ipt_upload_archive`, `ipt_publish_resource`, all-in-one `ipt_upload_and_publish()`
   (prompts for credentials; .Renviron supported).

## The GBIF leg of occurrence-publish (wraps this path conceptually)

- We produce an equivalent artifact — an occurrence-core DwC-A zip (occurrence.txt +
  dna_derived_data.txt + eMoF as applicable + meta.xml + eml.xml) — with our own Python
  builder, then emit a **ready-to-run command** the user executes on their IPT:
  ```
  Rscript -e 'eDNAbridge::ipt_upload_and_publish(archive="OUT_ZIP", ipt_url="https://YOUR.IPT/")'
  ```
- Validation convention adopted from eDNAbridge `val_validate_all_fields`: stop when
  error-level issues exist; warnings are acceptable to publish (PLAN §6: "Warnings-level
  issues acceptable").

## obistools conventions (reference)

- `obistools::check_onland`, `check_outliers`, `check_occurrences`: issue reports shaped
  `{field, level, message, row}` — the same shape used by crosscheck_report.json (§11.3) and
  this skill's validation reports.
- OBIS QC preview before IPT push happens locally (this skill's validate/), never via a
  scripted live push in v1.

## Testdata mapping cheat-sheet (eDNAbridge → this skill)

| eDNAbridge | occurrence-publish |
|---|---|
| `tests/testthat/testdata/dwc/occurence_core.txt` (tab-delimited, occurrenceID first) | `event.txt`/`occurrence.txt` files emitted by scripts/dwca_core.py |
| `expected_meta.xml` (id index 0, fieldsTerminatedBy tab) | same meta.xml shape (see ../dwca-profile/metaxml-sample.md) |
| `eml_base() + eml_set_title()` | `scripts/dwca_core.py:build_eml()` |
| `ipt_upload_and_publish()` | NOT implemented in v1 — emitted as a command string only |