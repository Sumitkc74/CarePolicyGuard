import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"

policy_files = sorted([f for f in POLICIES_DIR.glob("*.json") if f.stem.startswith(("LCD-", "NCD-", "OPD-"))])

for pf in policy_files:
    with open(pf, "r", encoding="utf-8") as f:
        d = json.load(f)
    pid = d["policy_id"]
    title = d["title"]
    print(f"'{pid}': {{")
    print(f"    'title': {title!r},")
    for i, c in enumerate(d["criteria"]):
        ccode = c["criterion_code"]
        ctype = c["criterion_type"]
        is_excl = c.get("is_exclusion", False)
        ent = c.get("entity_names", [])[0]
        op = c.get("operator")
        th = c.get("threshold")
        dur = c.get("min_duration_days")
        print(f"    'c{i+1}': ('{ccode}', '{ctype}', {is_excl}, {ent!r}, {op!r}, {th!r}, {dur!r}),")
    print("},")

