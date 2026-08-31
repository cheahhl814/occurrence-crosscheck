# docs-corpus/dna-derived-data-extension — GBIF DNA-derived data guidance

Source captured 2026-08-31: https://docs.gbif.org/publishing-dna-derived-data/en/
("Publishing DNA-derived data through biodiversity data platforms" — GBIF/OBIS community guide)
and https://manual.obis.org/dna_data.html (cross-referenced in ../obis-dna-data/).

## The five categories of genetic data

1. DNA-derived occurrences
2. Enriched occurrences
3. Targeted species detection
4. Name references
5. Metadata only

eDNA metabarcoding output (one row per taxon × site × record; relative read abundance) is
**Category 1: DNA-derived occurrences**.

## Extension definition

- Extension XML: http://rs.gbif.org/extension/gbif/1.0/dna_derived_data_2021-07-05.xml
- rowType URI: `http://rs.gbif.org/terms/1.0/DNADerivedData`
- Mixes MIxS terms into Darwin Core. Linked to occurrence core via `occurrenceID`
  (and to event core via `eventID` when using the Event Core pattern).

## Required / strongly recommended terms for eDNA + metabarcoding

| Term (DNA Derived class) | Meaning |
|---|---|
| `DNA_sequence` | The ASV/OTU sequence (most important field; enables OBIS sequence search) |
| `sop` | Standard operating procedure link(s) |
| `target_gene` | e.g. 18S, 16S, 12S, COI |
| `target_subfragment` | e.g. V9, MiFish-U |
| `pcr_primer_forward` / `pcr_primer_reverse` | primer sequences |
| `pcr_primer_name_forward` / `pcr_primer_name_reverse` | primer names |
| `pcr_primer_reference` | citation for primers |
| `Pcr_cond` | PCR conditions free text |
| `annealingTemp` / `annealinTempUnit` | annealing temperature (+ unit) |
| `ampliconSize` | expected amplicon length |
| `env_broad_scale` | ENVO class, e.g. `marine biome (ENVO:00000447)` |
| `env_local_scale` | e.g. `coastal water (ENVO:00001250)` |
| `env_medium` | e.g. `waterborne particulate matter (ENVO:01000436)` |
| `lib_layout` | `paired` / `single` |
| `seq_meth` | e.g. `Illumina MiSeq 2x250` |
| `otu_class_appr` | e.g. `dada2;1.14.0;ASV` (pipeline;version;unit type) |
| `otu_seq_comp_appr` | sequence computation approach |
| `otu_db` | reference database used for taxonomy |

## Occurrence-core terms to populate for DNA-derived data

- `organismQuantity` = reads of this sequence in this sample; `organismQuantityType` =
  "DNA sequence reads" (always — relative abundance, NOT organism abundance).
- `sampleSizeValue` = total reads in the sample; `sampleSizeUnit` = "DNA sequence reads".
- `associatedSequences` — link to archived raw reads (e.g. NCBI BioProject URL).
- `verificationStatus` / `identificationRemarks` — annotation confidence + reference DB.
- `identificationReferences` — pipeline publication link.
- `taxonConceptID` + `verbatimIdentification` — non-Linnean IDs (e.g. NCBI:txid9771).
- `materialSampleID` — links to physical sample.

## Unassigned/unknown sequences

Use `scientificName = "Biota incertae sedis"` (or lowest known rank), `scientificNameID` =
WoRMS LSID for that name (Biota incertae sedis = `urn:lsid:marinespecies.org:taxname:12`),
and keep the original annotation in `verbatimIdentification`.

## Naming note (works with the GBIF leg)

The GBIF leg of this skill publishes: occurrence core
(`basisOfRecord=MaterialSample`, organismQuantity etc.) + DNADerivedData extension linked by
`occurrenceID`. The OBIS leg additionally uses the Event Core pattern; see ../obis-dna-data/.