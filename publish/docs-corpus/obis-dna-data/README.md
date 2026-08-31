# docs-corpus/obis-dna-data — OBIS DNA data manual (Event Core + eMoF/OBIS-ENV-DATA pattern)

Source captured 2026-08-31: https://manual.obis.org/dna_data.html (full HTML captured verbatim
during build; highlights below). Companion chapters: https://manual.obis.org/data_sharing.html,
https://manual.obis.org/format.html. The Event-Core eDNA pattern was first published by OBIS in
July 2026 per PLAN §6.

## The OBIS eDNA structure (what obis-publish generates)

**Event Core with parent/child hierarchy** → Occurrence extension → DNA-derived data extension,
linked by `eventID` / `occurrenceID`:

```
survey/cruise  (eventID: CRU::MYCRUISE, parent null)
└─ station     (eventID: CRU::MYCRUISE::ST001, parentEventID: CRU::MYCRUISE)
   └─ sample   (eventID: ...::ST001::SMP1, parentEventID: ...station)
      └─ sequencing event (eventID: ...::SMP1::SEQ1, parentEventID: ...sample)
```

- Every event row carries `eventID` + `parentEventID` (empty for the root).
- Station events carry `decimalLatitude`/`decimalLongitude` (+ `footprintWKT` optional),
  `minimumDepthInMeters`/`maximumDepthInMeters`.
- Sequencing events carry `samplingProtocol`, `sampleSizeValue`, `sampleSizeUnit`
  (e.g. litres filtered), `eventDate`.
- Occurrence extension: `occurrenceID`, `basisOfRecord` (`MaterialSample`), `organismQuantity`
  (reads of sequence in sample), `organismQuantityType` = "DNA sequence reads",
  `scientificName`, `scientificNameID` (WoRMS LSID), `taxonRank`, `kingdom`…`genus`,
  `associatedSequences`. Links to parent sequencing event via `eventID` column → coreid.
- DNA-derived data extension: linked via `occurrenceID` (and `eventID`); terms per
  ../dna-derived-data-extension/README.md.

## eMoF / OBIS-ENV-DATA (measurementOrFact rows)

OBIS-ENV-DATA style ExtendedMeasurementOrFact extension, one row per measurement:

| Column | Content |
|---|---|
| `occurrenceID` | link to occurrence (coreid) |
| (optional `eventID`) | link to event |
| `measurementType` | e.g. `http://vocab.nerc.ac.uk/collection/P01/current/TEMPP901/` or a human label |
| `measurementValue` | e.g. `12.4` |
| `measurementUnit` | e.g. `http://vocab.nerc.ac.uk/collection/P06/current/UPAA/` |
| `measurementAccuracy` / `measurementDeterminedDate` / `measurementDeterminedBy` / `measurementMethod` / `measurementRemarks` | optional |

rowType: `http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact`.

**Bio-ORACLE environmental values slot in here naturally** (PLAN §6 synergy with Phase 1):
every `env_bio_*` column present in `enriched.parquet` becomes one eMoF row per occurrence
with measurementType = the layer name (e.g. `BO2_tempmin_ss`) and measurementValue = the float.
If no `env_*` columns are present the eMoF file is omitted entirely.

## OBIS-specific rules enforced by this skill

- **WoRMS is the only taxonomic backbone in OBIS.** This skill hard-rejects any record
  without a WoRMS-valid `scientificNameID` LSID (`urn:lsid:marinespecies.org:taxname:N`)
  per pinned decision (gate c).
- Unknown/unassigned taxa: `scientificName = "Biota incertae sedis"`,
  `scientificNameID = urn:lsid:marinespecies.org:taxname:12` + original name in
  `verbatimIdentification`.
- Sequences with no WoRMS AphiaID: per the manual a submitter *may* leave `scientificNameID`
  empty with `taxonConceptID` set — but the pinned decision for THIS skill is stricter
  (hard-reject), chosen so the ingest-time workaround is never needed. Deviation is intentional.
- OBIS uses WoRMS LSIDs; GBIF taxonKeys may be absent.
- Publishing is via an OBIS IPT instance upload (https://ipt.obis.org). This skill NEVER
  performs a live push in v1 — it emits ready-to-run commands (see ../ednabridge-conv/).

## Validation

Local structural checks only (see ../gbif-data-validator/README.md §OBIS-side): the OBIS QC
preview (`obistools`) conventions are eventID/parentEventID integrity, coordinate sanity for
marine records, depth ordering, and occurrence↔event linkage — mirrored in
`scripts/validate.py local_obis_checks`.