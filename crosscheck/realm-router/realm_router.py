#!/usr/bin/env python3
"""realm-router: reads params.json's `realm` and emits routing.json.

This is the ONLY place realm if-statements live (PLAN §4). Every downstream
sub-skill reads routing.json instead of branching on `realm` itself.

Usage: python3 realm_router.py <params.json> <out_routing.json>
"""
from __future__ import annotations
import json
import sys

# NOTE on WoRMS scope: PLAN §2's scope table describes WoRMS as also covering
# brackish/freshwater taxa "where a marine history exists". The PINNED
# battle-test contract (task prompt, realm-matrix section) is stricter and
# overrides that nuance: freshwater and terrestrial runs must NOT call WoRMS
# at all. call_worms is therefore gated strictly on realm == marine.
ROUTING_TABLE = {
    "marine": {
        "occurrence_sources": ["gbif", "obis"],
        "taxon_backbones": {"gbif": "required", "worms": "required", "fishbase": "optional-finfish"},
        "call_obis": True,
        "call_worms": True,
        "call_bio_oracle": True,
        "env_source": "bio-oracle",
        "env_column_prefix": "env_bio_",
        "env_layer_choice": "surface-or-benthic-from-fishbase-depth",
        "qc_checks": ["OUT_OF_RANGE", "ENVELOPE_VIOLATION", "GENUS_ONLY", "NOVEL_TAXON", "ON_LAND"],
        "missing_aphia_is_error": True,
        "obis_lookup": True,
    },
    "freshwater": {
        "occurrence_sources": ["gbif"],
        "taxon_backbones": {"gbif": "required", "worms": "skip", "fishbase": "optional-finfish"},
        "call_obis": False,
        "call_worms": False,
        "call_bio_oracle": False,
        "env_source": "worldclim-chelsa",
        "env_column_prefix": "env_wc_",
        "env_layer_choice": "elev-bioclim",
        "qc_checks": ["OUT_OF_RANGE", "ENVELOPE_VIOLATION", "GENUS_ONLY", "NOVEL_TAXON", "ON_LAND"],
        "missing_aphia_is_error": False,
        "obis_lookup": False,
    },
    "terrestrial": {
        "occurrence_sources": ["gbif"],
        "taxon_backbones": {"gbif": "required", "worms": "skip", "fishbase": "n/a"},
        "call_obis": False,
        "call_worms": False,
        "call_bio_oracle": False,
        "env_source": "worldclim-chelsa",
        "env_column_prefix": "env_wc_",
        "env_layer_choice": "elev-bioclim",
        # ON_LAND check does not apply to terrestrial (PLAN §4/scope table): terrestrial is
        # land-valid by definition, so it is omitted from qc_checks entirely rather than
        # included-but-always-false, keeping "checks that ran" self-documenting.
        "qc_checks": ["OUT_OF_RANGE", "ENVELOPE_VIOLATION", "GENUS_ONLY", "NOVEL_TAXON"],
        "missing_aphia_is_error": False,
        "obis_lookup": False,
    },
}


def route(realm: str) -> dict:
    if realm not in ROUTING_TABLE:
        raise ValueError(f"unknown realm {realm!r}; expected one of {sorted(ROUTING_TABLE)}")
    cfg = dict(ROUTING_TABLE[realm])
    cfg["realm"] = realm
    return cfg


def main() -> None:
    params_path, out_path = sys.argv[1], sys.argv[2]
    with open(params_path) as f:
        params = json.load(f)
    routing = route(params["realm"])
    with open(out_path, "w") as f:
        json.dump(routing, f, indent=2)
    print(f"realm-router: realm={params['realm']} -> {out_path}")


if __name__ == "__main__":
    main()
