---
name: validate-dwca
description: 'Sub-skill 4 of occurrence-publish: validates produced DwC-A zips. GBIF side: online submission to the GBIF Data Validator API (POST https://api.gbif.org/v1/validation, results via GET /v1/validation?key=) with a documented offline fallback to local structural checks (meta.xml/EML parse, zip-entry integrity, field mapping, rowType vocabulary). OBIS side: local structural checks only per the OBIS manual (never a live IPT push). Writes *_gbif_validation.json + *_obis_validation.json. Triggers: "validate dwca", "gbif data validator", "obis structural checks".'
version: 1.0.0
updated: "2026-08-31"
triggers:
  - "validate dwca"
  - "gbif data validator"
  - "obis structural checks"
  - "pre-publish validation"
---

# Sub-skill: validate-dwca

## Inputs / Outputs contract

| Artifact | Source | Required |
|---|---|---|
| `<run-dir>/*_gbif_dwca.zip` | gbif-publish | yes (GBIF leg) |
| `<run-dir>/*_obis_dwca.zip` | obis-publish | yes (OBIS leg, marine) |
| `<work>/out/*_gbif_validation.json` | this sub-skill | — (produced) |
| `<work>/out/*_obis_validation.json` | this sub-skill | — (produced) |

Implementation: `scripts/validate.py`.

## Procedure

1. **GBIF leg — online attempt (default):**
   - `POST https://api.gbif.org/v1/validation` (multipart `file=@<zip>`).
   - Response semantics (probed 2026-08-31, see docs-corpus/gbif-data-validator/):
     200/201 → JSON with a validation `key`; poll `GET https://api.gbif.org/v1/validation?key=<key>`
     until state ≠ RUNNING, then save the verbatim report.
     401/403 → `online_status: "auth_required"` (endpoint exists, anonymous submission denied).
     network error → `online_status: "unreachable"`.
   - On 401/403/offline → run the **documented fallback**: local structural checks (step 2) and
     mark `validation_mode: "local_fallback"` in the report. `--offline` skips the network call.
2. **Local structural checks (both legs, always recorded):**
   - zip opens; `meta.xml` + `eml.xml` present; both parse as XML;
   - EML has non-empty `<dataset>/<title>`, creator, pubDate;
   - every meta.xml `location` exists in the zip; every `field/@index` within the actual
     header length; term attributes are http(s) term URIs;
   - core rowType ∈ known vocabulary; extension files define a `coreid` link column;
   - every data row has the core id column non-empty.
3. **OBIS-side checks (local only, NEVER a live IPT push):** eventID uniqueness;
   parentEventID referential integrity + single connected root; occurrence coreids resolve to
   event rows; DNA-derived occurrenceIDs resolve; coordinates within [-90,90]/[-180,180];
   minDepth ≤ maxDepth; WoRMS LSID format re-check (mirrors gate c as a QC row).
   Issue rows use `{field, level, message, row}` (obis-data-qc style).
4. Write `*_gbif_validation.json` / `*_obis_validation.json` with an overall
   `verdict: GO | GO-WITH-WARNINGS | NO-GO` derived from issue levels:
   any `error` → NO-GO; only `warning` → GO-WITH-WARNINGS; else GO.

## Interpretation Guidelines

- **GO / GO-WITH-WARNINGS** → ready for the final ask-user confirm (user runs
  `work/publish_commands.sh`). Warnings-level issues are acceptable per PLAN §6.
- **NO-GO** → fix and re-run the failing publish sub-skill before any upload attempt.

## Ask-user stop points

| SP | Trigger | Resolution record |
|---|---|---|
| SP-V1 | Online validator auth-denied | Pinned: document fallback, run local checks, record `online_status`. Never fake an online result. |
| SP-V2 | Actual publish | Final human confirm — user executes `work/publish_commands.sh` themselves (v1 pinned: no live publishing calls from this skill). |

## Troubleshooting — Signature library

| Signature | Likely cause | Suggested fix |
|---|---|---|
| `HTTP 403` on validator POST | Anonymous submission denied | Use `--offline` local checks, or configure credentials; record auth_required. |
| `online_status: unreachable` | Network/firewall | `--offline`; review local checks; retry online later. |
| `meta.xml parse error` | Writer bug or hand-edited zip | Regenerate via the publish sub-skill. |
| `obis: parentEventID ... missing` | Hierarchy broken | Re-run obis-publish; never hand-edit the zip. |
| `validation key polling timed out` | Validator busy | Retry; the key stays valid at GET /v1/validation?key=. |

## Output contract

`*_gbif_validation.json` + `*_obis_validation.json` (machine) + console verdict (human).
Next: the user executes `work/publish_commands.sh` at the final ask-user stop point.