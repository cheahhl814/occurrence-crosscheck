#!/usr/bin/env python3
"""Self-update check for edna-crosscheck.

Diffs the deployed git SHA against origin/HEAD via `git fetch` — no GitHub
API call, no extra dependency, works air-gapped (reports OFFLINE/NO-ORIGIN
instead of failing). Wired to `pixi run update-check`.

Verdicts (exit code in parens):
  UP-TO-DATE   (0)  local HEAD matches origin/HEAD
  LOCAL-AHEAD  (0)  unpushed local commits; no action needed
  BEHIND-BY-N  (1)  upstream is N commits ahead -> rsync from @skills/occurrence-crosscheck/
  OFFLINE      (2)  git fetch failed (no network / no credentials)
  NO-ORIGIN    (2)  no `origin` remote configured
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    rc, local_sha = run(["git", "rev-parse", "HEAD"])
    if rc != 0:
        print("NO-ORIGIN: not a git repo (or no commits yet)")
        return 2

    rc, remotes = run(["git", "remote"])
    if "origin" not in remotes.split():
        print(f"NO-ORIGIN: no 'origin' remote configured. local_sha={local_sha}")
        return 2

    rc, _ = run(["git", "fetch", "origin"])
    if rc != 0:
        print(f"OFFLINE: git fetch failed. local_sha={local_sha}")
        return 2

    rc, origin_sha = run(["git", "rev-parse", "origin/HEAD"])
    if rc != 0:
        print(f"OFFLINE: no origin/HEAD ref. local_sha={local_sha}")
        return 2

    if local_sha == origin_sha:
        print(f"UP-TO-DATE: {local_sha}")
        return 0

    rc, ahead_count = run(["git", "rev-list", "--count", f"{local_sha}..origin/HEAD"])
    rc2, behind_count = run(["git", "rev-list", "--count", f"origin/HEAD..{local_sha}"])
    n_behind = int(ahead_count) if ahead_count.isdigit() else 0
    n_ahead_local = int(behind_count) if behind_count.isdigit() else 0

    if n_behind > 0:
        print(f"BEHIND-BY-{n_behind}: local={local_sha} origin/HEAD={origin_sha}")
        print("Fix: rsync -av --delete @skills/occurrence-crosscheck/ ~/.pi/agent/skills/edna-crosscheck/ ; diff -rq to verify")
        return 1
    if n_ahead_local > 0:
        print(f"LOCAL-AHEAD: {n_ahead_local} unpushed commit(s). local={local_sha}")
        return 0

    print(f"UP-TO-DATE: {local_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
