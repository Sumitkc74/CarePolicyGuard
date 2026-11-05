import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"
DEV_VIGNETTES_FILE = POLICIES_DIR / "dev_vignettes_extended.json"

from app.agents.pipeline import MultiAgentVerificationPipeline

pipeline = MultiAgentVerificationPipeline(db=None)

with open(DEV_VIGNETTES_FILE, "r", encoding="utf-8") as f:
    vignettes = json.load(f)

app_matches = 0
neg_matches = 0
neg_deferred = 0
app_deferred = 0

for v in vignettes:
    pid = v["policy_id"]
    exp = v["expected_decision"]
    narrative = v["ehr_narrative"]
    adj = pipeline.adjudicate_sync(patient_id="PT-TEST", policy_id=pid, ehr_narrative=narrative, execution_mode="declarative", save_record=False)
    act = adj.adjudication_decision.value

    is_match = (act == exp)
    if exp == "APPROVED":
        if is_match:
            app_matches += 1
        else:
            app_deferred += 1
            print(f"[APPROVED FAIL] {v['vignette_id']} ({pid}): act={act} status={adj.abstention_status} reason={adj.abstention_reason}")
    else:
        if is_match:
            neg_matches += 1
        else:
            neg_deferred += 1
            print(f"[NEGATIVE FAIL] {v['vignette_id']} ({pid}): act={act} status={adj.abstention_status} reason={adj.abstention_reason}")

print(f"\nAPPROVED matches: {app_matches}/42")
print(f"NEGATIVE matches: {neg_matches}/42 (Deferred to human: {neg_deferred})")

