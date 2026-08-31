#!/usr/bin/env bash
# Realm-matrix battle test (PLAN §9 acceptance criteria): runs the SAME
# synthetic fixture three times with --realm marine/freshwater/terrestrial,
# then verifies network-call assertions + schema conformance against the
# real output directories. Real network calls, no mocking.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$SKILL_DIR/test/fixtures/synthetic_asv.csv"
OUT_BASE="${1:-$SKILL_DIR/test/battle-test-out}"
rm -rf "$OUT_BASE"
mkdir -p "$OUT_BASE"

cd "$SKILL_DIR"
for realm in marine freshwater terrestrial; do
  echo "############ realm=$realm ############"
  pixi run crosscheck "$FIXTURE" "$realm" 12S "$OUT_BASE/$realm"
done

echo "############ verifying ############"
pixi run python3 test/verify_battle_test.py "$OUT_BASE/marine" "$OUT_BASE/freshwater" "$OUT_BASE/terrestrial"
