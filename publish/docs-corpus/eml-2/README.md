# docs-corpus/eml-2 — EML 2.x / GBIF Extended Metadata Profile

Source captured 2026-08-31: https://ipt.gbif.org/manual/en/ipt/latest/gbif-metadata-profile
(GBIF Extended Metadata Profile — "primarily based on the Ecological Metadata Language (EML)" 2.1.1).
See also https://eml.ecoinformatics.org/ and https://docs.gbif.org/publishing-dna-derived-data/en/.

The IPT/GBIF metadata doc inside a DwC-A must be named `eml.xml` (declared via
`<archive metadata="eml.xml">` in meta.xml). Namespace:
`eml://ecoinformatics.org/eml-2.1.1`.

## Minimum viable eml.xml skeleton (as emitted by scripts/dwca_core.py)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xmlns:dc="http://purl.org/dc/terms/"
         packageId="occurrence-publish/1.0" system="occurrence-publish"
         xsi:schemaLocation="eml://ecoinformatics.org/eml-2.1.1 https://rs.gbif.org/schema/eml-gbif-profile/1.3/eml.xsd">
  <dataset>
    <title>Dataset title (required)</title>
    <creator><individualName><surName>Required</surName></individualName></creator>
    <metadataProvider>...</metadataProvider>
    <pubDate>CCYY-MM-DD</pubDate>
    <language>en</language>
    <abstract><para>...</para></abstract>
    <keywordSet><keyword>...</keyword><keywordThesaurus>N/A</keywordThesaurus></keywordSet>
    <intellectualRights><para>license</para></intellectualRights>
    <contact>...</contact>
    <!-- coverage -->
    <coverage>
      <geographicCoverage>
        <geographicDescription>bbox of the run</geographicDescription>
        <boundingCoordinates>
          <westBoundingCoordinate>...</westBoundingCoordinate>
          <eastBoundingCoordinate>...</eastBoundingCoordinate>
          <northBoundingCoordinate>...</northBoundingCoordinate>
          <southBoundingCoordinate>...</southBoundingCoordinate>
        </boundingCoordinates>
      </geographicCoverage>
      <temporalCoverage><rangeOfDates><beginDate><calendarDate>...</calendarDate></beginDate>
        <endDate><calendarDate>...</calendarDate></endDate></rangeOfDates></temporalCoverage>
      <taxonomicCoverage> <!-- taxonomicClassification/taxonRankName/taxonRankValue --> </taxonomicCoverage>
    </coverage>
    <methods><methodStep><description><para>...</para></description></methodStep>
      <qualityControl><description><para>...</para></description></qualityControl></methods>
  </dataset>
  <additionalMetadata><metadata><gbif>...</gbif></metadata></additionalMetadata>
</eml:eml>
```

## Required elements (GBIF validator treats missing ones as ERRORS)

- `<dataset>` with `title`, `creator`, `pubDate`, `language`, `abstract`, `intellectualRights`, `contact`
- creator/contact use the EML party pattern: `individualName → givenName + surName`.
- `pubDate` ISO 8601 (CCYY or CCYY-MM-DD).
- `keywordSet` requires `keyword` AND `keywordThesaurus` together.

## Party fields (subset)

givenName, surName, organizationName, positionName, electronicMailAddress, deliveryPoint, city,
administrativeArea, postalCode, country, onlineUrl, role.

## Coverage fields

- Geographic: geographicDescription + boundingCoordinates (W/E/N/S decimal degrees).
- Temporal: rangeOfDates (beginDate/endDate calendarDate, ISO YYYY-MM-DD) or singleDateTime.
- Taxonomic: taxonomicClassification with taxonRankName + taxonRankValue (+ commonName); not nested.

## Methods

methodStep (repeatable), qualityControl, sampling (studyExtent, samplingDescription).