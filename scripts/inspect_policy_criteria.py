import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"

policy_files = sorted([f for f in POLICIES_DIR.glob("*.json") if f.stem.startswith(("LCD-", "NCD-", "OPD-"))])

for pf in policy_files:
    with open(pf, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"=== {data['policy_id']} : {data['title']} ===")
    for c in data["criteria"]:
        code = c["criterion_code"]
        name = c["name"]
        ctype = c["criterion_type"]
        is_excl = c.get("is_exclusion", False)
        entities = c.get("entity_names", [])
        thresh = f"{c.get('operator')} {c.get('threshold')} {c.get('target_unit')}" if ctype == "NUMERIC_THRESHOLD" else ""
        dur = f"{c.get('min_duration_days')} days" if ctype == "TEMPORAL_DURATION" else ""
        print(f"  [{code}] ({ctype}) {'[EXCLUSION]' if is_excl else ''} {name} | entities: {entities[:3]} | {thresh} {dur}")
    print()

