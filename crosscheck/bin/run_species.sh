#!/usr/bin/env bash
# run_species.sh — MODE A orchestrator: species list -> known-range envelopes.
#
# Inverts the OUT_OF_RANGE/ENVELOPE checks: "where does the literature+GBIF+OBIS
# say this species occurs, and what are its trait/env envelopes?" — useful to
# ground-truth a species list, build range maps, or as the reference-gap denominator.
#
# Usage: bin/run_species.sh <species_input> <realm> <out_dir> [record_limit]
#   species_input : .txt (one scientificName per line) or .csv/.tsv with a
#                   scientificName column
# Outputs (out_dir):
#   species_envelopes.csv  per species: global GBIF/OBIS counts, empirical
#                          extent bbox (sampled GBIF records), FishBase traits
#   review_queue.csv       ambiguous/unresolved names (never silently resolved)
#   params.json
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPECIES="${1:?species list required (.txt or .csv)}";
REALM="${2:?realm required (marine|freshwater|terrestrial)}"
OUT_DIR="${3:?out_dir required}"
LIMIT="${4:-120}"
WORK_DIR="$OUT_DIR/work"
MARKER="list"   # placeholder: envelope mode is marker-independent

mkdir -p "$OUT_DIR" "$WORK_DIR"

echo "== input adapter (species mode) =="
python3 "$SKILL_DIR/preflight/input_adapters.py" species "$SPECIES" "$REALM" "$MARKER" "$WORK_DIR"
PARAMS_JSON="$OUT_DIR/params.json"; cp "$WORK_DIR/params.json" "$PARAMS_JSON"

echo "== realm-router =="
python3 "$SKILL_DIR/realm-router/realm_router.py" "$PARAMS_JSON" "$WORK_DIR/routing.json"

echo "== taxon-resolve (standard chain, unchanged) =="
python3 "$SKILL_DIR/taxon-resolve/taxon_resolve.py" "$WORK_DIR/names.txt" "$WORK_DIR/routing.json" "$WORK_DIR"
cp "$WORK_DIR/review_queue.csv" "$OUT_DIR/review_queue.csv"

echo "== fishbase-traits (standard chain) =="
python3 "$SKILL_DIR/fishbase-traits/fishbase_traits.py" "$WORK_DIR/names.txt" "$WORK_DIR/routing.json" "$WORK_DIR" || echo "(fishbase-traits: offline or non-fish realm — continuing)"

echo "== range lookup (inverted query) =="
python3 "$SKILL_DIR/crosscheck/range_lookup.py" "$WORK_DIR/names.txt" "$WORK_DIR/routing.json" "$WORK_DIR" "$LIMIT"

echo "== done: $OUT_DIR =="
ls "$OUT_DIR"