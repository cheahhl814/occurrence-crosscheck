#!/usr/bin/env python3
"""occurrence-publish — shared plain-Python DwC-A writer (v1.0.0).

Builds Darwin Core Archive zips with ONLY the standard library:
  - data files are tab-delimited text written from a list of row dicts
  - meta.xml is hand-built XML (Darwin Core Text Guide schema)
  - eml.xml is EML 2.1.1 (GBIF Extended Metadata Profile) hand-built XML

No eDNAbridge dependency (pinned decision). Used by gbif_publish.py and obis_publish.py.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, tostring

from xml.etree.ElementTree import Element, SubElement, tostring

DWC = "http://rs.tdwg.org/dwc/terms/"
GBIF_EXT = "http://rs.gbif.org/terms/1.0/"
DNA_ROWTYPE = "http://rs.gbif.org/terms/1.0/DNADerivedData"
EMOF_ROWTYPE = "http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact"
OCC_ROWTYPE = DWC + "Occurrence"
EVENT_ROWTYPE = DWC + "Event"

# rowTypes validate.py treats as known
KNOWN_ROWTYPES = {OCC_ROWTYPE, EVENT_ROWTYPE, DNA_ROWTYPE, EMOF_ROWTYPE}

LICENSE_TEXT = ("http://creativecommons.org/licenses/by/4.0/legalcode "
                "- Creative Commons Attribution 4.0")


def occurrence_id(event_date, lat, lon, sci_name, asv_id=""):
    """Deterministic stable occurrenceID from the row key fields."""
    raw = "|".join(str(x) for x in (event_date, lat, lon, sci_name, asv_id))
    return "occ:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


# ------------------------------------------------------------- data-file writer

def resolve_term(term):
    """Fully-qualify a term name: DwC class terms get the DwC namespace;
    DNA-derived data / GBIF extension terms get the GBIF extension namespace;
    already-qualified URIs pass through."""
    if term.startswith("http://") or term.startswith("https://"):
        return term
    if term in GBIF_EXT_TERMS:
        return GBIF_EXT + term
    return DWC + term


# Terms that live in the GBIF DNA-derived data extension namespace
GBIF_EXT_TERMS = {
    "DNA_sequence", "sop", "target_gene", "target_subfragment",
    "pcr_primer_forward", "pcr_primer_reverse",
    "pcr_primer_name_forward", "pcr_primer_name_reverse",
    "pcr_primer_reference", "Pcr_cond", "annealingTemp", "annealingTempUnit",
    "ampliconSize", "env_broad_scale", "env_local_scale", "env_medium",
    "lib_layout", "seq_meth", "otu_class_appr", "otu_seq_comp_appr", "otu_db",
}


def write_tsv(rows, columns):
    """Tab-delimited UTF-8 text buffer with a header row."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, delimiter="\t",
                       lineterminator="\n", quoting=csv.QUOTE_MINIMAL,
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    return buf.getvalue().encode("utf-8")


# -------------------------------------------------------------------- meta.xml

DWCA_NS = "http://rs.tdwg.org/dwc/text/"


def build_meta_xml(core, extensions):
    """Hand-built meta.xml (Darwin Core Text Guide / eDNAbridge convention).

    core = {"location": "occurrence.txt", "rowType": OCC_ROWTYPE, "columns": [...], "id_index": 0}
    ext  = {"location": "dna.txt", "rowType": DNA_ROWTYPE, "columns": [...],
            "coreid_index": 0, "coreid_term": "occurrenceID"}

    Elements are created IN the dwc/text namespace; the default namespace is
    registered so the serialized output is
      <archive xmlns="http://rs.tdwg.org/dwc/text/" metadata="eml.xml">... (unqualified tags)
    — exactly the real DwC-A on-disk convention — and round-trips through
    namespace-aware parsers.
    """
    ET.register_namespace("", DWCA_NS)
    archive = Element(f"{{{DWCA_NS}}}archive", {"metadata": "eml.xml"})
    attrs_base = {"encoding": "UTF-8", "fieldsTerminatedBy": "\t",
                  "linesTerminatedBy": "\n", "fieldsEnclosedBy": "\"",
                  "ignoreHeaderLines": "1"}

    def q(tag):
        return f"{{{DWCA_NS}}}{tag}"

    def file_block(parent, spec, is_core):
        attrs = {**attrs_base, "rowType": spec["rowType"]}
        el = SubElement(parent, q("core") if is_core else q("extension"), attrs)
        files_el = SubElement(el, q("files"))
        loc = SubElement(files_el, q("location"))
        loc.text = spec["location"]
        return el

    core_el = file_block(archive, core, is_core=True)
    SubElement(core_el, q("id"), {"index": str(core.get("id_index", 0))})
    for i, term in enumerate(core["columns"]):
        if i == core.get("id_index", 0):
            continue
        SubElement(core_el, q("field"), {"index": str(i), "term": resolve_term(term)})

    for ext in extensions:
        ext_el = file_block(archive, ext, is_core=False)
        SubElement(ext_el, q("coreid"), {"index": str(ext["coreid_index"])})
        for i, term in enumerate(ext["columns"]):
            if i == ext["coreid_index"]:
                SubElement(ext_el, q("field"),
                           {"index": str(i),
                            "term": DWC + ext.get("coreid_term", "occurrenceID")})
            else:
                SubElement(ext_el, q("field"), {"index": str(i), "term": resolve_term(term)})

    return (b'<?xml version="1.0" encoding="UTF-8"?>\n'
            + tostring(archive, encoding="utf-8"))


# ---------------------------------------------------- EML 2.1.1 (GBIF profile)

LICENSE_TEXT = ("http://creativecommons.org/licenses/by/4.0/legalcode "
                "- Creative Commons Attribution 4.0 International")


def build_eml(title, abstract, bbox, begin_date, end_date, creator_surname,
              creator_given="Data", package_id="occurrence-publish/1.0",
              method_text=None, marker=None, taxonomic_coverage=None,
              contact_email=None):
    """Minimal-but-valid GBIF EML 2.1.1 profile document (hand-built XML).

    `contact_email` (SP-4, propagated from crosscheck preflight via
    params.json:user_email) is required for GBIF/IPT publication —
    IPTs reject datasets without a contactable individual. Recorded
    once on the `contact` party (the dataset's primary contact) and
    mirrored on `creator` + `metadataProvider` so any of the three
    roles can be reached about the dataset.
    """
    eml_ns = "eml://ecoinformatics.org/eml-2.1.1"
    eml = Element("eml:eml", {
        "xmlns:eml": eml_ns,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:dc": "http://purl.org/dc/terms/",
        "packageId": package_id, "system": "occurrence-publish",
        "xsi:schemaLocation":
            eml_ns + " https://rs.gbif.org/schema/eml-gbif-profile/1.3/eml.xsd",
    })
    ds = SubElement(eml, "dataset")
    SubElement(ds, "title").text = title

    def party(tag):
        p = SubElement(ds, tag)
        ind = SubElement(p, "individualName")
        SubElement(ind, "givenName").text = creator_given
        SubElement(ind, "surName").text = creator_surname
        if contact_email:
            ea = SubElement(p, "electronicMailAddress")
            ea.text = contact_email
        return p

    party("creator")
    party("metadataProvider")
    party("contact")
    SubElement(ds, "pubDate").text = end_date
    SubElement(ds, "language").text = "en"
    ab = SubElement(ds, "abstract")
    SubElement(ab, "para").text = abstract
    ks = SubElement(ds, "keywordSet")
    SubElement(ks, "keyword").text = "eDNA"
    SubElement(ks, "keywordThesaurus").text = "N/A"
    ir = SubElement(ds, "intellectualRights")
    SubElement(ir, "para").text = LICENSE_TEXT

    cov = SubElement(ds, "coverage")
    geo = SubElement(cov, "geographicCoverage")
    SubElement(geo, "geographicDescription").text = "bounding box of the run"
    bc = SubElement(geo, "boundingCoordinates")
    for tag, val in (("westBoundingCoordinate", bbox[0]),
                     ("southBoundingCoordinate", bbox[1]),
                     ("eastBoundingCoordinate", bbox[2]),
                     ("northBoundingCoordinate", bbox[3])):
        SubElement(bc, tag).text = str(val)
    tcov = SubElement(cov, "temporalCoverage")
    rod = SubElement(tcov, "rangeOfDates")
    for parent_tag, d in (("beginDate", begin_date), ("endDate", end_date)):
        node = SubElement(rod, parent_tag)
        SubElement(node, "calendarDate").text = d
    tax = SubElement(cov, "taxonomicCoverage")
    SubElement(tax, "generalTaxonomicCoverage").text = "eDNA ASV taxa"
    tcl = SubElement(tax, "taxonomicClassification")
    SubElement(tcl, "taxonRankName").text = "taxa"
    names = sorted({t for t in (taxonomic_coverage or []) if t})[:50]
    SubElement(tcl, "taxonRankValue").text = ", ".join(names) if names else "unspecified"

    meth = SubElement(ds, "methods")
    step = SubElement(meth, "methodStep")
    desc = SubElement(step, "description")
    SubElement(desc, "para").text = method_text or (
        "eDNA sampling processed by nf-edna; ASV taxonomy cross-checked by edna-crosscheck; "
        "DwC-A published via occurrence-publish v1.0.0.")
    qc = SubElement(meth, "qualityControl")
    qc_desc = SubElement(qc, "description")
    SubElement(qc_desc, "para").text = (
        "Flagged occurrences required explicit sign-off before publish (occurrence-publish gate a).")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(eml, encoding="utf-8")


# -------------------------------------------------------------------------- zip

def build_dwca_zip(out_path, core, extensions, eml_xml, meta_xml):
    """Write the DwC-A zip.

    core = {"location": "occurrence.txt", "content": bytes}
    ext  = {"location": "dna.txt", "content": bytes}
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(core["location"], core["content"])
            for ext in extensions:
                z.writestr(ext["location"], ext["content"])
            z.writestr("eml.xml", eml_xml)
            z.writestr("meta.xml", meta_xml)
    return out_path


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()