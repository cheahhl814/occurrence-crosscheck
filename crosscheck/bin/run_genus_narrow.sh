#!/usr/bin/env bash
# run_genus_narrow.sh — MODE D: genus-only ASVs -> candidate species.
#
# For ASVs classified only to genus ("Genus sp." / bare genus from idtaxa),
# narrows the species-ID space to the species OF THAT GENUS that are actually
# recorded within a buffer around the detection site(s), ranked by regional
# corroboration. Pairs with nf-edna reference-gap reporting (PLAN §4).
#
# Usage:
#   bin/run_genus_narrow.sh <input.csv> <realm> <out_dir> [--buffer-km N] [max_sp]
#   input.csv : scientificName ("Genus sp." or "Genus"), plus per-row
#               decimalLatitude,decimalLongitude (site coords are what makes
#               the narrowing regional — required)
#
# Output: out_dir/genus_candidates.csv (genus, candidate_species, rank,
#         n_records_in_buffer, sources) + params.json
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="${1:?input.csv required (scientificName + decimalLatitude/decimalLongitude)}"
REALM="${2:?realm required (marine|freshwater|terrestrial)}"
OUT_DIR="${3:?out_dir required}"
shift 3

BUFFER_KM="0"
if [ "${1:-}" = "--buffer-km" ]; then BUFFER_KM="$2"; shift 2; fi
MAX_SP="${1:-40}"
WORK_DIR="$OUT_DIR/work"
mkdir -p "$OUT_DIR" "$WORK_DIR"

python3 "$SKILL_DIR/crosscheck/genus_narrow.py" "$INPUT" "$REALM" "$OUT_DIR" "$BUFFER_KM" "$MAX_SP"

echo "== done: $OUT_DIR =="
ls "$OUT_DIR"