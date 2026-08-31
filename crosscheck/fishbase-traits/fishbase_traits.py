#!/usr/bin/env python3
"""fishbase-traits: bulk-pulls FishBase depth/trophic/body-size traits for
the unique scientificName list via fishbase_pull.R (rfishbase, CRAN — see
preflight.md §FishBase client decision), then exposes a lookup table other
sub-skills (taxon-resolve, crosscheck) join against.

For realm == terrestrial this is a pass-through: no R call is made, trait
columns are null with reason "terrestrial: fishbase n/a" (PLAN §4).

Usage: python3 fishbase_traits.py <names_file> <routing.json> <work_dir>
Writes: <work_dir>/fishbase_pull.json  {scientificName: {SpecCode, DepthRangeShallow, DepthRangeDeep, Length, trophic_level}}
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    names_file, routing_path, work_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(routing_path) as f:
        routing = json.load(f)

    out_json = work_dir / "fishbase_pull.json"

    if routing["realm"] == "terrestrial":
        out_json.write_text("{}")
        print("fishbase-traits: realm=terrestrial, pass-through (fishbase n/a)")
        return

    rscript = HERE / "fishbase_pull.R"
    try:
        subprocess.run(
            ["Rscript", str(rscript), names_file, str(out_json)],
            check=True, capture_output=True, text=True, timeout=420,
            # ponytail: 420s covers rfishbase's cold-start duckdb-extension download (observed to add
            # ~1-2 min on a fresh R session in this sandbox); raise further if a slower network proves
            # this insufficient in practice, or switch to a persistent duckdb home (see docs-corpus/
            # fishbase/README.md) to avoid re-downloading extensions every subprocess call.
        )
    except FileNotFoundError:
        print("fishbase-traits: Rscript not found; emitting empty trait table (fishbase unavailable)", file=sys.stderr)
        out_json.write_text("{}")
        return
    except subprocess.CalledProcessError as e:
        print(f"fishbase-traits: fishbase_pull.R failed rc={e.returncode}: {e.stderr[-2000:]}", file=sys.stderr)
        out_json.write_text("{}")
        return
    except subprocess.TimeoutExpired:
        print("fishbase-traits: fishbase_pull.R timed out; emitting empty trait table", file=sys.stderr)
        out_json.write_text("{}")
        return

    if not out_json.exists():
        out_json.write_text("{}")
    n = len(json.loads(out_json.read_text() or "{}"))
    print(f"fishbase-traits: {n} taxa with FishBase trait rows -> {out_json}")


if __name__ == "__main__":
    main()
