# docs-corpus/dwca-profile — Darwin Core Archive text profile (occurrence core + extensions + meta.xml)

Sources captured 2026-08-31:
- https://ipt.gbif.org/manual/en/ipt/latest/dwca-guide (IPT manual, "Creating a Darwin Core Archive")
- http://rs.tdwg.org/dwc/terms/guides/text/index.htm (Darwin Core Text Guide — metafile format)
- https://github.com/gbif/eDNAbridge `tests/testthat/testdata/dwc/expected_meta.xml` (worked example)

A DwC-A is a ZIP archive containing:
1. One **core** data file (CSV/TXT) — for occurrence-publish: `http://rs.tdwg.org/dwc/terms/Occurrence` rowType (GBIF leg) or `http://rs.tdwg.org/dwc/terms/Event` (OBIS Event Core).
2. One file per **extension**: Occurrence extension (`http://rs.tdwg.org/dwc/terms/Occurrence`),
   DNA-derived data (`http://rs.gbif.org/terms/1.0/DNADerivedData`),
   ExtendedMeasurementOrFact / eMoF (`http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact`).
3. **meta.xml** — the star-schema map (see `metaxml-sample.md`).
4. **eml.xml** — EML 2.x metadata (see ../eml-2/).

## Manual DwC-A procedure (per IPT dwca-guide)

1. Prepare delimited text file(s) — the metafile maps columns to Darwin Core terms, so column
   headers do not need to be DwC terms (using DwC terms as headers reduces errors).
2. Create meta.xml — either by hand (Darwin Core Text Guide) or scripted. Must declare, per file:
   `encoding`, `fieldsTerminatedBy`, `linesTerminatedBy`, `fieldsEnclosedBy`, `ignoreHeaderLines`,
   `rowType`; one `<id>` / `<coreid>` link column per extension; one `<field index="N" term="URI">`
   per mapped column. `id` links core rows; extension `<coreid>` references the core `id`.
3. Create eml.xml (GBIF Extended Metadata Profile — see ../eml-2/).
4. Zip data files + meta.xml + eml.xml together (files may sit flat or in a directory inside the
   zip; the `location` attributes in meta.xml must match the zip entry paths).

## Worked meta.xml example (from eDNAbridge testdata, occurrence core only)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/" metadata="eml.xml">
  <core encoding="UTF-8" fieldsTerminatedBy="\t" linesTerminatedBy="\n"
        fieldsEnclosedBy="" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files><location>occurrence_core.txt</location></files>
    <id index="0"/>
    <field index="1" term="http://rs.tdwg.org/dwc/terms/basisOfRecord"/>
    <field index="2" term="http://rs.tdwg.org/dwc/terms/organismQuantity"/>
    <field index="10" term="http://rs.tdwg.org/dwc/terms/scientificName"/>
    <!-- ... one field per column ... -->
  </core>
</archive>
```

## Key extension rowTypes (v1 of this skill)

| File | rowType | Link |
|---|---|---|
| occurrence core (GBIF) | `http://rs.tdwg.org/dwc/terms/Occurrence` | `<id>` = occurrenceID |
| Event core (OBIS) | `http://rs.tdwg.org/dwc/terms/Event` | `<id>` = eventID; parentEventID builds hierarchy |
| Occurrence extension | `http://rs.tdwg.org/dwc/terms/Occurrence` | `<coreid>` = core eventID |
| DNA-derived data | `http://rs.gbif.org/extension/gbif/1.0/dna_derived_data_2021-07-05.xml` rowType `http://rs.gbif.org/terms/1.0/DNADerivedData` | coreid = occurrenceID and/or eventID |
| eMoF / OBIS-ENV-DATA | `http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact` | coreid = occurrenceID (+ optional eventID linkage) |

GBIF accepts any well-formed archive structurally; taxonomic/coordinate issues surface as
validator warnings (see ../gbif-data-validator/).