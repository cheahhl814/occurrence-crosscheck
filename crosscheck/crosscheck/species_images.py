#!/usr/bin/env python3
"""Citable species-image fetcher for the occurrence-crosscheck meta-skill.

For each full binomial on a run's species list, fetch ONE embeddable image with a
machine-readable license and record the full citation chain (image URL, license,
creator/rightsHolder, occurrence/taxon page).

Policy (flags-never-drops):
  - iNaturalist default_photo first (curator-chosen, CC-licensed, clean portrait),
    GBIF occurrence media as breadth fallback (96% coverage measured on 2024K1).
  - CC0 / CC-BY -> flag "cc-best"; CC-BY-NC(-SA/ND) -> "by-nc" (citation-required,
    fine for internal reports); "all rights reserved" or missing license rows keep
    the image URL but are flagged and NOT cached (publish leg must exclude them).
  - Ambiguous taxa (Sillago sp. 2 SS-2021) -> flag "flag-ambiguous-taxon"; species
    with no image anywhere -> "flag-no-image".

Cache-warm safe (2024K1 audit lesson D-audit-1): species_images.csv already
contains a row with a local file present -> reused untouched instead of a
header-only rebuild.

Usage:
  python3 species_images.py <species_list.csv|txt> <work_dir>

Outputs: <work_dir>/species_images.csv (§11.8 manifest)
         <work_dir>/images/<slug>.jpg  (local cache)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from netlog import NetLog  # noqa: E402

UA = {"User-Agent": "AiX-BIO-occurrence-crosscheck (edna image fetcher)"}

CC_URL_RE = re.compile(r"creativecommons\.org/(licenses|publicdomain)/[\w\-./]+")
ARR_RE = re.compile(r"\ball rights reserved\b", re.I)
IMG_EXT = (".jpg", ".jpeg", ".png")

FLAG_AMBIGUOUS = "flag-ambiguous-taxon"
FLAG_NO_IMAGE = "flag-no-image"

SPDX_BY_CODE = {
    "cc0": "CC0-1.0", "cc-by": "CC-BY-4.0", "cc-by-sa": "CC-BY-SA-4.0",
    "cc-by-nc": "CC-BY-NC-4.0", "cc-by-nc-sa": "CC-BY-NC-SA-4.0",
    "cc-by-nd": "CC-BY-ND-4.0", "cc-by-nc-nd": "CC-BY-NC-ND-4.0",
}
SPDX_BY_URL = {
    "publicdomain/zero": "CC0-1.0",
    "licenses/by/4.0": "CC-BY-4.0", "licenses/by/3.0": "CC-BY-3.0",
    "licenses/by-sa/4.0": "CC-BY-SA-4.0", "licenses/by-nc/4.0": "CC-BY-NC-4.0",
    "licenses/by-nc/3.0": "CC-BY-NC-3.0", "licenses/by-nc-sa/4.0": "CC-BY-NC-SA-4.0",
}

MANIFEST_FIELDS = ["scientificName", "source", "image_url", "local_file", "bytes", "license",
                   "license_url", "creator", "rightsHolder", "attribution", "occurrence_url",
                   "flag", "fetched_at"]

RESTRICTED_RANK = {"cc-best": 0, "by-nc": 1, "flag-no-license": 2, "flag-all-rights-reserved": 3,
                   "flag-no-image": 4}


def license_of(rec: dict) -> str:
    return (rec.get("license_url") or rec.get("license") or "").strip()


def license_flag(license_str: str, inat_code: str = "") -> str:
    """Map a license string / iNat license code to a manifest flag.

    cc-best            CC0 or plain CC-BY(-SA) -> embed with attribution
    by-nc              CC-BY-NC(-SA/ND)        -> attribution-required, internal-ok
    flag-all-...       "all rights reserved"
    flag-no-license    missing/unrecognized
    """
    if inat_code:
        code = inat_code.lower()
        if code == "cc0":
            return "cc-best"
        if not code.startswith("cc"):
            return "flag-no-license"
        return "by-nc" if ("nc" in code or "nd" in code) else "cc-best"
    if not license_str:
        return "flag-no-license"
    if ARR_RE.search(license_str):
        return "flag-all-rights-reserved"
    m = CC_URL_RE.search(license_str)
    if not m:
        return "flag-no-license"
    g = m.group(0)
    if "publicdomain/zero" in g:
        return "cc-best"
    sub = g.split("licenses/")[-1].rstrip("/")
    if "nc" in sub or "nd" in sub:
        return "by-nc"
    if sub.startswith("by"):
        return "cc-best"
    return "flag-no-license"


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())


def _get_json(net: NetLog, url: str, src: str):
    import requests
    try:
        resp = net.get(src, url, timeout=30)
        return resp.json()
    except Exception as e:  # noqa: BLE001
        print(f"WARN: {type(e).__name__} fetching {url[:80]}", file=sys.stderr)
        return None


def _img_bytes(net: NetLog, url: str):
    import requests
    try:
        src = "gbif" if "gbif.org" in url else "inaturalist"
        resp = net.get(src, url, timeout=60)
        return resp.content if resp.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _blank(name: str) -> dict:
    return {"scientificName": name, "source": "", "image_url": "", "local_file": "", "bytes": "",
            "license": "", "license_url": "", "creator": "", "rightsHolder": "",
            "attribution": "", "occurrence_url": "", "flag": "", "fetched_at": ""}


def from_inat(net: NetLog, name: str) -> dict | None:
    t = _get_json(net, f"https://api.inaturalist.org/v1/taxa?q={quote(name)}&per_page=5", "inaturalist")
    if not isinstance(t, dict):
        return None
    for cand in t.get("results", []):
        if (cand.get("name") or "").lower() != name.lower():
            continue
        ph = cand.get("default_photo") or {}
        url = ph.get("medium_url") or ph.get("url")
        if not url:
            return None
        code = (ph.get("license_code") or "").lower()
        rec = _blank(name)
        rec.update(source="inaturalist", image_url=url,
                   license=SPDX_BY_CODE.get(code, code),
                   license_url=ph.get("license_url") or "",
                   creator=ph.get("attribution") or "",
                   rightsHolder=cand.get("attribution") or "",
                   attribution=ph.get("attribution") or "",
                   occurrence_url=f"https://www.inaturalist.org/taxa/{cand.get('id', '')}")
        return rec
    return None


def from_gbif(net: NetLog, name: str) -> dict | None:
    m = _get_json(net, f"https://api.gbif.org/v1/species/match?name={quote(name)}", "gbif")
    if not isinstance(m, dict) or not m.get("usageKey"):
        return None
    occ = _get_json(net, f"https://api.gbif.org/v1/occurrence/search"
                         f"?taxonKey={m['usageKey']}&mediaType=StillImage&limit=100", "gbif")
    if not isinstance(occ, dict):
        return None
    best, best_rank = None, 10
    for o in occ.get("results", []):
        for med in o.get("media", []):
            if med.get("type") != "StillImage":
                continue
            url = med.get("identifier") or ""
            if not url.lower().endswith(IMG_EXT):
                continue
            f = license_flag(med.get("license") or "")
            rank = RESTRICTED_RANK.get(f, 4)
            if rank < best_rank:
                best_rank = rank
                best = _blank(name)
                best.update(source="gbif", image_url=url,
                            license=SPDX_BY_URL.get(med.get("license", "").split("creativecommons.org/")[-1].rstrip("/"),
                                                    med.get("license") or ""),
                            license_url=med.get("license") or "",
                            creator=med.get("creator") or med.get("rightsHolder") or "",
                            rightsHolder=med.get("rightsHolder") or "",
                            attribution=med.get("creator") or med.get("rightsHolder") or "",
                            occurrence_url=f"https://www.gbif.org/occurrence/{o.get('key', '')}")
    return best


def read_species(list_path: Path) -> tuple[list[str], set[str]]:
    p = open(list_path, newline="")
    names: list[str] = []
    if list_path.suffix.lower() == ".csv":
        for row in csv.DictReader(p):
            for col in ("scientificName", "scientific_name", "ScientificName"):
                if row.get(col):
                    n = re.sub(r"\s+", " ", row[col].strip())
                    if n and n not in names:
                        names.append(n)
                    break
    else:
        for line in p:
            n = re.sub(r"\s+", " ", line.strip())
            if n and n not in names:
                names.append(n)
    p.close()
    ambiguous = {n for n in names if n.count(" ") != 1 or " sp." in n or n.endswith(" sp")}
    return names, ambiguous


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(2)
    list_path, work_dir = Path(args[0]), Path(args[1])
    names, ambiguous = read_species(list_path)
    (work_dir / "images").mkdir(parents=True, exist_ok=True)
    net = NetLog(work_dir)

    manifest = work_dir / "species_images.csv"
    prev: dict[str, dict] = {}
    if manifest.exists():  # cache-warm rerun: keep verified rows (D-audit-1 lesson)
        try:
            for r in csv.DictReader(open(manifest)):
                if r.get("local_file") and (work_dir / r["local_file"]).exists():
                    prev[r["scientificName"]] = {k: r.get(k, "") for k in MANIFEST_FIELDS}
        except Exception:
            prev = {}

    rows: list[dict] = []
    for n in names:
        cached = prev.get(n)
        if cached:
            rows.append(cached)
            continue
        if n in ambiguous:
            rec = _blank(n)
            rec["flag"] = FLAG_AMBIGUOUS
            rows.append(rec)
            continue
        rec = from_inat(net, n)
        if rec is not None:
            code = rec["license"].lower()
            if not code.startswith("cc"):  # ARR / none on iNat -> GBIF may hold a CC shot
                gb = from_gbif(net, n)
                if gb is not None and license_flag(gb["license_url"]) in ("cc-best", "by-nc"):
                    rec = gb
                else:
                    rec["flag"] = "flag-all-rights-reserved" if ARR_RE.search(rec["creator"] or "") else "flag-no-license"
            time.sleep(0.05)
        else:
            rec = from_gbif(net, n)
            time.sleep(0.1)
        if rec is None:
            rec = _blank(n)
        if rec["image_url"]:
            if rec["source"] == "inaturalist":
                rec["flag"] = license_flag(rec["license_url"], rec["license"])
            elif rec["source"] == "gbif":
                rec["flag"] = license_flag(rec["license_url"])
            else:
                rec["flag"] = "flag-no-license"
            if rec["flag"] not in ("flag-all-rights-reserved", "flag-no-license"):
                data = _img_bytes(net, rec["image_url"])
                if data:
                    rel = f"images/{_slug(n)}.jpg"
                    (work_dir / rel).write_bytes(data)
                    rec["local_file"], rec["bytes"] = rel, len(data)
        else:
            rec["flag"] = FLAG_NO_IMAGE
        rec["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows.append(rec)

    with open(manifest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in MANIFEST_FIELDS})

    n_img = sum(1 for r in rows if r.get("local_file"))
    n_flag = sum(1 for r in rows if str(r.get("flag", "")).startswith("flag"))
    print(f"species-images: {len(rows)} species processed, {n_img} images cached, {n_flag} flagged -> {manifest}")


if __name__ == "__main__":
    main()