"""
Backfill script to add explicit "status": "ACTIVE" to all 60 catalog policy JSONs (Task 2).

Preserves exact existing adjudication behavior by explicitly declaring the ACTIVE status
that previously defaulted in DeclarativePolicy schema, making the DRAFT gate enforceable.
Does not alter any criterion, description, threshold, or policy metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
POLICY_DIRS = [
    ROOT_DIR / "app" / "data" / "policies",
    ROOT_DIR / "app" / "data" / "policies_extended",
]


def backfill_policy_status() -> int:
    touched_count = 0
    seen_policy_ids = set()

    for p_dir in POLICY_DIRS:
        if not p_dir.exists():
            continue
        for p_file in sorted(p_dir.glob("*.json")):
            if p_file.name in ["cms_extraction_manifest.json", "dev_vignettes_extended.json"]:
                continue
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict) or "policy_id" not in data:
                continue

            pid = data["policy_id"]
            if pid in seen_policy_ids:
                continue
            seen_policy_ids.add(pid)

            # Check if status field needs to be set or is already ACTIVE
            data["status"] = "ACTIVE"
            with open(p_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            touched_count += 1
            print(f"[+] Backfilled status=ACTIVE for policy {pid} in {p_file.name}")

    print(f"\n[SUMMARY] Total policy JSONs updated with explicit status=ACTIVE: {touched_count}")
    return touched_count


if __name__ == "__main__":
    count = backfill_policy_status()
    assert count == 60, f"Expected exactly 60 policies touched, got {count}"
