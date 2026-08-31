# docs-corpus/gbif-data-validator — GBIF Data Validator + OBIS-side checks

Sources captured 2026-08-31:
- https://www.gbif.org/tools/data-validator (tool page; HTML 403 to scripting clients — human-facing)
- https://techdocs.gbif.org/en/openapi/v1/validator (Validator API technical documentation)
- https://github.com/gbif/gbif-data-validator (source repo; checks now part of GBIF pipelines)
- Live probing of api.gbif.org (curl, 2026-08-31) — endpoint behavior verified:
  - `POST https://api.gbif.org/v1/validation` — multipart file upload of a DwC-A zip.
    Live probe returned **HTTP 403 "Access is denied"** for anonymous multipart POST →
    the endpoint exists but requires credentials (or a whitelisted client) for submission.
  - `GET https://api.gbif.org/v1/validation?key=...` — retrieves a validation result
    (live GET with no key returned 400 "Failed to convert 'key'" — endpoint exists).
  - `GET https://api.gbif.org/v1/validation/download/{key}` exists for download-style validations.
  - GBIF community forum (2021) stated there was no public API; the newer validator service
    exposes the above REST surface but anonymous access is denied.

## How validate/ uses this (per pinned decision)

1. **Online attempt**: `scripts/validate.py` POSTs the produced `*_gbif_dwca.zip` to
   `https://api.gbif.org/v1/validation` as multipart `file`. If the response is 200/201 with a
   JSON body containing a key, it polls `GET /v1/validation?key=<key>` until a report is
   returned (state RUNNING/SUCCEEDED/FAILED), then saves it to `*_gbif_validation.json`.
   - 401/403 → recorded in the report as `online_status: "auth_required"`, then fallback (2).
   - network error → `online_status: "unreachable"`, then fallback (2).
2. **Fallback (documented)**: local-only structural checks run against the zip:
   - zip entry checks: `meta.xml` present + parses; `eml.xml` present + parses + `<dataset>/<title>` non-empty;
   - every file referenced by meta.xml `location` exists in the zip;
   - every `<field index="N">` is a valid term URI; column indices in range of the actual file's
     header length;
   - core `rowType` is a known rowType; extension files have a `coreid` linking column;
   - occurrence core basisOfRecord ∈ DwC b.o.r. vocabulary (non-empty for checked rows);
   - `scientificNameID` LSID format check for OBIS packages.
   These are structural checks only — they do NOT replace the online validator's interpretation
   (taxonomy matching, coordinate interpretation), which is exactly why the online step is
   preferred and its result is recorded verbatim.

## OBIS-side validation (never a live IPT push)

`local_obis_checks` mirrors the obistools/manual QC conventions (see ../obis-dna-data/):
- eventID uniqueness + parentEventID referential integrity + single connected hierarchy;
- occurrence extension eventIDs all resolve to a core event row;
- DNA-derived + eMoF occurrenceIDs all resolve to an occurrence row;
- decimalLatitude/Longitude present on station events and within [-90,90]/[-180,180];
- minimumDepthInMeters ≤ maximumDepthInMeters when both present;
- every occurrence has a WoRMS LSID scientificNameID (gate c is enforced upstream,
  re-checked here as a QC row);
- result written to `*_obis_validation.json` with issue rows
  `{field, level, message, row}` (obis-data-qc style).