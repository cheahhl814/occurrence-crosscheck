#!/usr/bin/env bash
# edna-crosscheck orchestrator (bash-first, per pinned decision — no
# Nextflow runner, this skill is I/O-bound).
#
# Usage: bin/run-crosscheck.sh <input.csv> <realm> <marker> <out_dir> \
#                              --user-email <email> \
#                              [work_dir] \
#                              [ --bbox MINLON MINLAT MAXLON MAXLAT | --buffer-km N | --buffer-deg D ]
#
# Chain (hard order per PLAN §4/§7):
#   preflight -> realm-router -> taxon-resolve -> fishbase-traits ->
#   env-extract -> occurrence-lookup -> crosscheck
#
# SP-4 (user_email): mandatory. The agent MUST ask the user for this
# before invoking the orchestrator. Do not invent, do not default.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_CSV="${1:?input.csv required}"
REALM="${2:?realm required (marine|freshwater|terrestrial)}"
MARKER="${3:?marker required}"
OUT_DIR="${4:?out_dir required}"

shift 4
# Parse --user-email (SP-4, mandatory) out of the remaining args.
USER_EMAIL=""
BUFFER_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --user-email)
      USER_EMAIL="${2:?--user-email requires a value}"
      shift 2
      ;;
    --user-email=*)
      USER_EMAIL="${1#--user-email=}"
      shift
      ;;
    *)
      BUFFER_ARGS+=("$1")
      shift
      ;;
  esac
done
if [ -z "$USER_EMAIL" ]; then
  echo "run-crosscheck: FAIL --user-email is required (SP-4 — GBIF/OBIS API contact-attribution policy). Re-run with --user-email <address>." >&2
  exit 1
fi
# Optional buffer-zone declaration (preflight phase, PLAN §4): pass through any of
#   --bbox MINLON MINLAT MAXLON MAXLAT | --buffer-km N | --buffer-deg D
# (first arg after --user-email may still be the legacy work_dir positional)
WORK_DIR="$OUT_DIR/work"
if [ ${#BUFFER_ARGS[@]} -gt 0 ] && [[ "${BUFFER_ARGS[0]}" != --* ]]; then
  WORK_DIR="${BUFFER_ARGS[0]}"
  BUFFER_ARGS=("${BUFFER_ARGS[@]:1}")
fi

mkdir -p "$OUT_DIR" "$WORK_DIR"
PARAMS_JSON="$OUT_DIR/params.json"
ROUTING_JSON="$WORK_DIR/routing.json"
NAMES_FILE="$WORK_DIR/names.txt"

echo "== preflight =="
python3 "$SKILL_DIR/preflight/preflight.py" "$INPUT_CSV" "$REALM" "$MARKER" "$PARAMS_JSON" \
    --user-email "$USER_EMAIL" \
    ${BUFFER_ARGS[@]+"${BUFFER_ARGS[@]}"}
# ^ buffer zone is declared at preflight: --buffer-km N (pad extent by N km, lon-corrected
#   at mean latitude) | --bbox MINLON MINLAT MAXLON MAXLAT (explicit) | default 0.25-deg pad.

# Mirror params.json into work_dir so per-sub-skill scripts (which use work_dir
# as their primary state root) can read user_email + buffer zone without
# needing to know about the out_dir layout. Single source of truth: $PARAMS_JSON.
cp "$PARAMS_JSON" "$WORK_DIR/params.json"

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
if isinstance(fb, list):  # fishbase_traits emits [] when nothing resolved (shape bug)
    fb = {d.get("scientificName") or d.get("ScientificName", ""): d for d in fb if isinstance(d, dict)}
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
