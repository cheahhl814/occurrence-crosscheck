#!/usr/bin/env bash
# edna-crosscheck orchestrator (bash-first, per pinned decision — no
# Nextflow runner, this skill is I/O-bound).
#
# Usage: bin/run-crosscheck.sh <input.csv> <realm> <marker> <out_dir> [work_dir]
#
# Chain (hard order per PLAN §4/§7):
#   preflight -> realm-router -> taxon-resolve -> fishbase-traits ->
#   env-extract -> occurrence-lookup -> crosscheck
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_CSV="${1:?input.csv required}"
REALM="${2:?realm required (marine|freshwater|terrestrial)}"
MARKER="${3:?marker required}"
OUT_DIR="${4:?out_dir required}"
WORK_DIR="${5:-$OUT_DIR/work}"

mkdir -p "$OUT_DIR" "$WORK_DIR"
PARAMS_JSON="$OUT_DIR/params.json"
ROUTING_JSON="$WORK_DIR/routing.json"
NAMES_FILE="$WORK_DIR/names.txt"

echo "== preflight =="
python3 "$SKILL_DIR/preflight/preflight.py" "$INPUT_CSV" "$REALM" "$MARKER" "$PARAMS_JSON"

echo "== realm-router =="
python3 "$SKILL_DIR/realm-router/realm_router.py" "$PARAMS_JSON" "$ROUTING_JSON"

# unique scientificName list
python3 - "$INPUT_CSV" "$NAMES_FILE" <<'PY'
import csv, sys
inp, out = sys.argv[1], sys.argv[2]
names = set()
with open(inp) as f:
    for row in csv.DictReader(f):
        names.add(row["scientificName"])
with open(out, "w") as f:
    f.write("\n".join(sorted(names)) + "\n")
PY

echo "== taxon-resolve =="
python3 "$SKILL_DIR/taxon-resolve/taxon_resolve.py" "$NAMES_FILE" "$ROUTING_JSON" "$WORK_DIR"
cp "$WORK_DIR/review_queue.csv" "$OUT_DIR/review_queue.csv"

echo "== fishbase-traits =="
python3 "$SKILL_DIR/fishbase-traits/fishbase_traits.py" "$NAMES_FILE" "$ROUTING_JSON" "$WORK_DIR"

# join trait_depth_max_m onto the occurrence rows so env-extract can pick surface/benthic
POINTS_CSV="$WORK_DIR/points_with_depth.csv"
python3 - "$INPUT_CSV" "$WORK_DIR/fishbase_pull.json" "$POINTS_CSV" <<'PY'
import csv, json, sys
inp, fb_json, out = sys.argv[1], sys.argv[2], sys.argv[3]
fb = json.loads(open(fb_json).read() or "{}")
with open(inp) as f:
    rows = list(csv.DictReader(f))
for r in rows:
    entry = fb.get(r["scientificName"], {})
    r["trait_depth_max_m"] = entry.get("DepthRangeDeep", "")
fieldnames = list(rows[0].keys()) if rows else ["scientificName", "decimalLatitude", "decimalLongitude", "trait_depth_max_m"]
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
PY

echo "== env-extract =="
python3 "$SKILL_DIR/env-extract/env_extract.py" "$POINTS_CSV" "$ROUTING_JSON" "$PARAMS_JSON" "$WORK_DIR"

echo "== occurrence-lookup =="
python3 "$SKILL_DIR/crosscheck/occurrence_lookup.py" "$NAMES_FILE" "$ROUTING_JSON" "$PARAMS_JSON" "$WORK_DIR"

echo "== crosscheck =="
python3 "$SKILL_DIR/crosscheck/crosscheck.py" "$INPUT_CSV" "$WORK_DIR" "$ROUTING_JSON" "$PARAMS_JSON" "$OUT_DIR"

echo "== done: $OUT_DIR =="
ls -la "$OUT_DIR"
