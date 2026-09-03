#!/usr/bin/env bash
# input_adapters.py — MODE B: coordinates -> expected species (inverted query)
#!/usr/bin/env bash
# run_coordinates.sh — MODE B orchestrator: bare coordinates -> expected species.
#
# Inverts the OUT_OF_RANGE check: instead of "is this detection inside the
# known range?", asks "which species does the realm-routed sources say should
# be here?" (the regional-checklist workflow, crosswalk+flags attached).
#
# Usage: bin/run_coordinates.sh <points.csv> <realm> <out_dir>
#                              --user-email <email>
#                              [radius_deg] [max_taxa]
#   points.csv : decimalLatitude,decimalLongitude (or lat/lon) rows, optional point_id
# Outputs (out_dir):
#   expected_species.csv   point x species: backbone IDs + match status + counts
#   review_queue.csv       ambiguous/unresolved taxa (never silently resolved)
#   env_snapshot.csv       realm-routed env values at each point
#   params.json
#
# SP-4: --user-email is mandatory. The agent MUST ask the user before
# invoking this orchestrator. Do not invent, do not default.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POINTS="${1:?points.csv required (decimalLatitude,decimalLongitude)}"
REALM="${2:?realm required (marine|freshwater|terrestrial)}"
OUT_DIR="${3:?out_dir required}"
shift 3
USER_EMAIL=""
RADIUS="0.5"
MAX_TAXA="200"
# Parse --user-email (SP-4) out of remaining args.
ARGS=()
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
      ARGS+=("$1")
      shift
      ;;
  esac
done
if [ -z "$USER_EMAIL" ]; then
  echo "run_coordinates: FAIL --user-email is required (SP-4). Re-run with --user-email <address>." >&2
  exit 1
fi
# Remaining args: [radius_deg] [max_taxa]
RADIUS="${ARGS[0]:-0.5}"
MAX_TAXA="${ARGS[1]:-200}"
WORK_DIR="$OUT_DIR/work"
MARKER="checklist"   # placeholder: mode B is marker-independent

mkdir -p "$OUT_DIR" "$WORK_DIR"

echo "== input adapter (coords mode) =="
python3 "$SKILL_DIR/preflight/input_adapters.py" coords "$POINTS" "$REALM" "$MARKER" "$WORK_DIR" --user-email "$USER_EMAIL" "$RADIUS"
PARAMS_JSON="$OUT_DIR/params.json"; cp "$WORK_DIR/params.json" "$PARAMS_JSON"

echo "== realm-router =="
python3 "$SKILL_DIR/realm-router/realm_router.py" "$PARAMS_JSON" "$WORK_DIR/routing.json"

echo "== checklist builder (inverted query) =="
python3 "$SKILL_DIR/crosscheck/checklist_builder.py" "$WORK_DIR/points.csv" "$WORK_DIR/routing.json" "$PARAMS_JSON" "$WORK_DIR" "$MAX_TAXA"

echo "== taxon-resolve (standard chain, unchanged) =="
python3 "$SKILL_DIR/taxon-resolve/taxon_resolve.py" "$WORK_DIR/names.txt" "$WORK_DIR/routing.json" "$WORK_DIR"
cp "$WORK_DIR/review_queue.csv" "$OUT_DIR/review_queue.csv"

echo "== fishbase-traits (optional enrich) =="
python3 "$SKILL_DIR/fishbase-traits/fishbase_traits.py" "$WORK_DIR/names.txt" "$WORK_DIR/routing.json" "$WORK_DIR" || echo "(fishbase-traits: offline or non-fish realm — continuing)"

echo "== join expected taxa x backbone results =="
python3 - "$WORK_DIR" "$OUT_DIR" <<'PY'
import csv, json, sys
from pathlib import Path
work, out = Path(sys.argv[1]), Path(sys.argv[2])

raw = json.loads((work / "checklist_raw.json").read_text())
cw = {}
if (work / "crosswalk_cache.sqlite").exists():
    import sqlite3
    con = sqlite3.connect(work / "crosswalk_cache.sqlite")
    for name, accepted, key, aphia, status in con.execute(
            "SELECT scientificName, acceptedScientificName, gbif_taxonKey, worms_AphiaID, taxon_match_status FROM crosswalk"):
        cw[name] = (accepted, key, aphia, status)
    con.close()

fb = json.loads((work / "fishbase_pull.json").read_text()) if (work / "fishbase_pull.json").exists() else {}
if isinstance(fb, list):  # fishbase_traits emits [] when nothing resolved
    fb = {d.get("scientificName") or d.get("ScientificName", ""): d for d in fb if isinstance(d, dict)}

rows = []
for point_id, entry in raw.items():
    for src in ("obis_taxa", "gbif_taxa"):
        for t in entry.get(src) or []:
            n = t["name"]
            resolved = cw.get(n) or cw.get(_resolved_key(cw, n)) or (None, None, None, "unresolved")
            fb_e = fb.get(n, {})
            rows.append({"point_id": point_id, "source": src.removesuffix("_taxa"),
                         "expectedScientificName": n,
                         "n_records_expected": t.get("n_records", ""),
                         "acceptedScientificName": resolved[0] or "",
                         "gbif_taxonKey": resolved[1] or "",
                         "worms_AphiaID": resolved[2] or "",
                         "taxon_match_status": resolved[3],
                         "trait_depth_max_m": fb_e.get("DepthRangeDeep", "")})

def _resolved_key(cw, n):  # tolerate small key variations from facet names
    return n

fieldnames = ["point_id", "source", "expectedScientificName", "n_records_expected",
              "acceptedScientificName", "gbif_taxonKey", "worms_AphiaID",
              "taxon_match_status", "trait_depth_max_m"]
with open(out / "expected_species.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
print(f"join: {len(rows)} point-x-taxon rows -> {out}/expected_species.csv")
PY

echo "== env snapshot at points =="
python3 "$SKILL_DIR/env-extract/env_extract.py" "$WORK_DIR/points_geo.csv" "$WORK_DIR/routing.json" "$PARAMS_JSON" "$WORK_DIR" && \
  cp "$WORK_DIR/env_values.csv" "$OUT_DIR/env_snapshot.csv"

echo "== done: $OUT_DIR =="
ls "$OUT_DIR"